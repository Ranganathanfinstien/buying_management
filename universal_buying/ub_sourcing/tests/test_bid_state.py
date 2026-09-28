"""Bid state machine (V-14.1), Bid Status mapping and AC-13.1 default deadline."""

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import add_days, add_to_date, get_datetime, get_time, getdate, now_datetime, nowdate

from universal_buying.ub_sourcing.bidding import (
	BID_AWARDED,
	BID_OPEN,
	BID_REJECTED,
	BID_UNDER_EVALUATION,
	bid_status_for_workflow,
	get_bid_state,
	get_default_bid_deadline,
	reminder_seconds,
)
from universal_buying.universal_buying.settings import get_setting


def rfq(**kw):
	base = {"docstatus": 1, "workflow_state": "Open", "ub_bid_status": "Open",
		"ub_bid_deadline": add_days(now_datetime(), 5)}
	base.update(kw)
	return frappe._dict(base)


class TestBidState(UnitTestCase):
	def test_open_before_deadline(self):
		state = get_bid_state(rfq())
		self.assertEqual(state.state, "open")
		self.assertFalse(state.closed)

	def test_closing_soon_inside_reminder_window(self):
		seconds = reminder_seconds()
		if not seconds:
			self.skipTest("bid_reminder_hours is 0")
		state = get_bid_state(rfq(ub_bid_deadline=add_to_date(now_datetime(), seconds=seconds // 2)))
		self.assertEqual(state.state, "closing_soon")
		self.assertFalse(state.closed)

	def test_closed_after_deadline(self):
		state = get_bid_state(rfq(ub_bid_deadline=add_to_date(now_datetime(), minutes=-1)))
		self.assertEqual(state.state, "closed")
		self.assertTrue(state.closed)

	def test_draft_is_not_open(self):
		state = get_bid_state(rfq(docstatus=0, workflow_state="Draft"))
		self.assertEqual(state.state, "not_open")
		self.assertTrue(state.closed)

	def test_cancelled(self):
		self.assertEqual(get_bid_state(rfq(docstatus=2)).state, "cancelled")

	def test_awarded_and_rejected_lock(self):
		self.assertEqual(get_bid_state(rfq(workflow_state="Awarded")).state, "awarded")
		self.assertEqual(get_bid_state(rfq(ub_bid_status="Awarded")).state, "awarded")
		self.assertEqual(get_bid_state(rfq(workflow_state="Rejected")).state, "rejected")
		self.assertTrue(get_bid_state(rfq(workflow_state="Rejected")).closed)

	def test_any_approval_tier_locks_bidding(self):
		for wf in ("Pending Dept Head Approval", "Pending Final Approval", "Some Old Tier"):
			state = get_bid_state(rfq(workflow_state=wf, ub_bid_status="Under Evaluation"))
			self.assertEqual(state.state, "under_evaluation", wf)
			self.assertTrue(state.closed)

	def test_correction_required_locked_until_extended(self):
		locked = get_bid_state(rfq(workflow_state="Correction Required", ub_bid_status="Under Evaluation"))
		self.assertEqual(locked.state, "under_evaluation")
		reopened = get_bid_state(rfq(workflow_state="Correction Required", ub_bid_status="Open"))
		self.assertEqual(reopened.state, "open")
		lapsed = get_bid_state(rfq(workflow_state="Correction Required", ub_bid_status="Open",
			ub_bid_deadline=add_to_date(now_datetime(), minutes=-5)))
		self.assertEqual(lapsed.state, "under_evaluation")

	def test_bid_status_follows_workflow(self):
		self.assertEqual(bid_status_for_workflow("Open"), BID_OPEN)
		self.assertEqual(bid_status_for_workflow("Pending SCM Head Approval"), BID_UNDER_EVALUATION)
		self.assertEqual(bid_status_for_workflow("Correction Required"), BID_UNDER_EVALUATION)
		self.assertEqual(bid_status_for_workflow("Awarded"), BID_AWARDED)
		self.assertEqual(bid_status_for_workflow("Rejected"), BID_REJECTED)
		self.assertIsNone(bid_status_for_workflow("Draft"))

	def test_default_deadline_from_settings(self):
		days = int(get_setting("bid_deadline_default_days", default=7) or 0)
		at = get_time(get_setting("bid_deadline_default_time", default="17:00:00") or "17:00:00")
		deadline = get_default_bid_deadline()
		self.assertEqual(getdate(deadline), getdate(add_days(nowdate(), days)))
		self.assertEqual(get_datetime(deadline).time().replace(microsecond=0), at.replace(microsecond=0))
