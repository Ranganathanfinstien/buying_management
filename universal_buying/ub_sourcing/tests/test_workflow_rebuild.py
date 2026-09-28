"""RFQ approval workflow built from the settings tier table (BRD v2 8.2)."""

import frappe
from frappe.tests import IntegrationTestCase

from universal_buying.ub_sourcing.workflow import (
	ACTION_APPROVE,
	ACTION_AWARD,
	ACTION_REJECT,
	ACTION_RESUBMIT,
	ACTION_SEND,
	ACTION_SEND_BACK,
	ACTION_SUBMIT,
	AWARD_CONDITION,
	RFQ_WORKFLOW,
	SEND_CONDITION,
	SQ_WORKFLOW,
	STATE_AWARDED,
	STATE_CORRECTION,
	STATE_DRAFT,
	STATE_OPEN,
	STATE_REJECTED,
	build_rfq_workflow_definition,
	build_sq_workflow_definition,
	get_final_state,
	rebuild_rfq_workflow,
	rebuild_sq_workflow,
)


def fake_settings(tiers, award_role="CEO"):
	return frappe._dict({
		"award_role": award_role,
		"rfq_approval_tiers": [frappe._dict(role=r, state_name=s) for r, s in tiers],
	})


TIERS = [
	("Department Head", "Pending Dept Head Approval"),
	("SCM Head", "Pending SCM Head Approval"),
	("CEO", "Pending Final Approval"),
]


def transitions(defn, state=None, action=None):
	return [t for t in defn["transitions"]
		if (state is None or t["state"] == state) and (action is None or t["action"] == action)]


class TestRFQWorkflowDefinition(IntegrationTestCase):
	def test_states_follow_tiers(self):
		defn = build_rfq_workflow_definition(fake_settings(TIERS))
		names = list(dict.fromkeys(s["state"] for s in defn["states"]))
		self.assertEqual(names, [STATE_DRAFT, STATE_OPEN, *[s for _r, s in TIERS], STATE_CORRECTION, STATE_REJECTED, STATE_AWARDED])
		docstatus = {s["state"]: s["doc_status"] for s in defn["states"]}
		self.assertEqual(docstatus[STATE_DRAFT], "0")
		self.assertTrue(all(docstatus[s] == "1" for s in names if s != STATE_DRAFT))

	def test_chain_and_final_award(self):
		defn = build_rfq_workflow_definition(fake_settings(TIERS))
		self.assertTrue(transitions(defn, STATE_DRAFT, ACTION_SUBMIT))
		send = transitions(defn, STATE_OPEN, ACTION_SEND)
		self.assertTrue(send and all(t["next_state"] == TIERS[0][1] and t["condition"] == SEND_CONDITION for t in send))
		first = transitions(defn, TIERS[0][1], ACTION_APPROVE)[0]
		self.assertEqual((first["next_state"], first["allowed"]), (TIERS[1][1], TIERS[0][0]))
		self.assertFalse(transitions(defn, TIERS[-1][1], ACTION_APPROVE))
		award = transitions(defn, TIERS[-1][1], ACTION_AWARD)
		self.assertEqual(len(award), 1)
		self.assertEqual(award[0]["next_state"], STATE_AWARDED)
		self.assertEqual(award[0]["allowed"], "CEO")
		self.assertEqual(award[0]["condition"], AWARD_CONDITION)

	def test_every_tier_can_reject_and_send_back(self):
		defn = build_rfq_workflow_definition(fake_settings(TIERS))
		for role, state in TIERS:
			rej = transitions(defn, state, ACTION_REJECT)
			back = transitions(defn, state, ACTION_SEND_BACK)
			self.assertTrue(any(t["allowed"] == role and t["next_state"] == STATE_REJECTED for t in rej), state)
			self.assertTrue(any(t["allowed"] == role and t["next_state"] == STATE_CORRECTION for t in back), state)
		resubmit = transitions(defn, STATE_CORRECTION, ACTION_RESUBMIT)
		self.assertTrue(resubmit and all(t["next_state"] == TIERS[0][1] for t in resubmit))

	def test_award_role_differs_from_last_tier(self):
		defn = build_rfq_workflow_definition(fake_settings(TIERS[:2], award_role="Managing Director"))
		final = TIERS[1][1]
		self.assertEqual(get_final_state(fake_settings(TIERS[:2])), final)
		self.assertEqual(transitions(defn, final, ACTION_AWARD)[0]["allowed"], "Managing Director")
		self.assertTrue(any(t["allowed"] == "Managing Director" for t in transitions(defn, final, ACTION_REJECT)))

	def test_empty_table_falls_back_to_single_final_tier(self):
		defn = build_rfq_workflow_definition(fake_settings([]))
		self.assertTrue(transitions(defn, "Pending Final Approval", ACTION_AWARD))

	def test_reserved_state_name_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			build_rfq_workflow_definition(fake_settings([("CEO", "Open")]))

	def test_orphan_states_are_kept(self):
		defn = build_rfq_workflow_definition(fake_settings(TIERS), extra_states=["Pending Legacy Approval"])
		self.assertIn("Pending Legacy Approval", {s["state"] for s in defn["states"]})
		self.assertTrue(transitions(defn, "Pending Legacy Approval", ACTION_SEND_BACK))

	def test_sq_workflow_uses_award_role(self):
		defn = build_sq_workflow_definition(fake_settings(TIERS, award_role="Managing Director"))
		self.assertTrue(all(t["allowed"] == "Managing Director" for t in defn["transitions"]))
		approved = next(s for s in defn["states"] if s["state"] == "Approved")
		self.assertEqual((approved["update_field"], approved["update_value"]), ("ub_sq_status", "Approved"))


class TestRFQWorkflowRebuild(IntegrationTestCase):
	def tearDown(self):
		rebuild_rfq_workflow()
		rebuild_sq_workflow()
		super().tearDown()

	def test_rebuild_creates_workflow_and_masters(self):
		tiers = [("Department Head", "Pending UB Test Tier One"), ("CEO", "Pending UB Test Final")]
		wf = rebuild_rfq_workflow(fake_settings(tiers))
		self.assertEqual(wf.name, RFQ_WORKFLOW)
		self.assertEqual(wf.document_type, "Request for Quotation")
		self.assertTrue(wf.is_active)
		states = {s.state for s in wf.states}
		for _role, state in tiers:
			self.assertIn(state, states)
			self.assertTrue(frappe.db.exists("Workflow State", state))
		for action in (ACTION_SUBMIT, ACTION_SEND, ACTION_APPROVE, ACTION_REJECT, ACTION_SEND_BACK, ACTION_RESUBMIT, ACTION_AWARD):
			self.assertTrue(frappe.db.exists("Workflow Action Master", action), action)

		# rebuilding with other tiers replaces the chain on the same workflow
		wf = rebuild_rfq_workflow(fake_settings([("CEO", "Pending UB Test Only")]))
		self.assertEqual(frappe.db.count("Workflow", {"document_type": "Request for Quotation", "is_active": 1}), 1)
		self.assertIn("Pending UB Test Only", {s.state for s in wf.states})
		self.assertNotIn("Pending UB Test Tier One", {s.state for s in wf.states})

	def test_sq_workflow_rebuild(self):
		wf = rebuild_sq_workflow(fake_settings(TIERS))
		self.assertEqual(wf.name, SQ_WORKFLOW)
		self.assertEqual(wf.document_type, "Supplier Quotation")
