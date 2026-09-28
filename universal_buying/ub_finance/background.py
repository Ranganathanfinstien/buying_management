"""Background submit / cancel for large Purchase Invoices (BRD v2 design rule 5).

Based on the earlier ``background_document_action.py``. The document is locked in the
request, the action runs in the ``long`` queue and the user gets a realtime message on
success or failure. Only used when the invoice has more rows than the
``background_submit_rows`` setting (0 = never).
"""

import frappe
from frappe import _
from frappe.utils import cint

from universal_buying.universal_buying.settings import get_setting

SUBMIT_TIMEOUT = 4600
CANCEL_TIMEOUT = 2000


def should_run_in_background(doc):
	if frappe.flags.in_test or frappe.flags.in_import or frappe.flags.in_patch or frappe.flags.in_migrate:
		return False
	if doc.flags.get("ub_run_now") or doc.is_new():
		return False
	limit = cint(get_setting("background_submit_rows", company=doc.get("company"), default=0))
	return bool(limit) and len(doc.get("items") or []) > limit


def enqueue_document_action(doc, action, timeout):
	"""Lock the document and enqueue the inner action (``_submit`` / ``_cancel``).

	Raises frappe.DocumentLockedError when the document is already queued."""
	internal_action = f"_{action}" if hasattr(doc, f"_{action}") else action
	doc.check_if_locked()
	doc.lock()
	frappe.enqueue(
		"universal_buying.ub_finance.background.execute_document_action",
		queue="long",
		timeout=timeout,
		enqueue_after_commit=True,
		doctype=doc.doctype,
		name=doc.name,
		action=internal_action,
		notify_user=frappe.session.user,
	)


def queue_action_with_message(doc, action):
	timeout = SUBMIT_TIMEOUT if action == "submit" else CANCEL_TIMEOUT
	try:
		enqueue_document_action(doc, action, timeout)
		doc.flags.background_action_queued = True
		frappe.msgprint(
			_("{0} has {1} rows, so it is being processed in the background. You will be notified when it completes.").format(
				doc.name, len(doc.items)
			),
			indicator="blue",
			alert=True,
		)
	except frappe.DocumentLockedError:
		frappe.msgprint(
			_("{0} {1} is already queued or being processed in the background.").format(doc.doctype, doc.name),
			indicator="orange",
			alert=True,
		)
	return doc


def execute_document_action(doctype, name, action, notify_user=None):
	"""Background worker: unlock, run the action, notify the user via realtime."""
	doc = frappe.get_doc(doctype, name)
	doc.unlock()
	doc.flags.ub_run_now = True
	label = _("Submission") if "submit" in action else _("Cancellation")
	try:
		getattr(doc, action)()
	except Exception:
		frappe.db.rollback()
		msg = frappe.message_log[-1].get("message") if frappe.message_log else ("<pre>" + frappe.get_traceback() + "</pre>")
		doc.add_comment("Comment", _("Background {0} failed").format(label) + "<br><br>" + str(msg))
		frappe.db.commit()
		if notify_user:
			frappe.publish_realtime(
				"msgprint",
				{
					"message": _("{0} of {1} {2} failed").format(label, doctype, frappe.bold(name)) + "<br><br>" + str(msg),
					"title": _("Background Job Failed"),
					"indicator": "red",
				},
				user=notify_user,
			)
	else:
		if notify_user:
			done = _("submitted") if "submit" in action else _("cancelled")
			frappe.publish_realtime(
				"msgprint",
				{
					"message": _("{0} {1} has been {2}").format(doctype, frappe.bold(name), done),
					"title": _("Success"),
					"indicator": "green",
					"alert": 1,
				},
				user=notify_user,
			)
	doc.notify_update()
