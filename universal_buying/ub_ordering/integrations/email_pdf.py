"""Email PDF connector: sends the PO print as a PDF to the supplier."""

import frappe
from frappe import _

from universal_buying.ub_ordering.integrations.base import SupplierConnector
from universal_buying.ub_ordering.permissions import supplier_portal_users


class EmailPDFConnector(SupplierConnector):
	label = "Email PDF"

	def _recipients(self):
		emails = [e.strip() for e in (self.channel.email_to or "").replace(",", "\n").splitlines() if e.strip()]
		if not emails:
			emails = [frappe.db.get_value("User", u, "email") for u in supplier_portal_users(self.po.supplier)]
		if not emails and self.po.get("contact_email"):
			emails = [self.po.contact_email]
		if not emails:
			emails = [frappe.db.get_value("Supplier", self.po.supplier, "email_id")]
		emails = [e for e in emails if e]
		if not emails:
			frappe.throw(_("No email address for supplier {0}. Set one on the Supplier Channel.").format(self.po.supplier))
		return emails

	def _send(self, subject):
		frappe.sendmail(
			recipients=self._recipients(), subject=subject,
			message=_("Please find attached Purchase Order {0}.").format(self.po.name),
			attachments=[frappe.attach_print("Purchase Order", self.po.name, print_format=self.channel.print_format or None)],
			reference_doctype="Purchase Order", reference_name=self.po.name,
		)

	def send_order(self):
		self._send(_("Purchase Order {0}").format(self.po.name))
		self.record("Sent", self.requested_rows("Sent"))
		self.set_status("Sent")
		frappe.msgprint(_("Purchase Order emailed to the supplier."), alert=True, indicator="green")
		return "Sent"

	def send_amendment(self):
		self._send(_("Amended Purchase Order {0}").format(self.po.name))
		self.record("Amendment", self.requested_rows("Amendment Sent"))
		self.set_status("Amendment Sent")
		frappe.msgprint(_("Amended Purchase Order emailed to the supplier."), alert=True, indicator="green")
		return "Amendment Sent"
