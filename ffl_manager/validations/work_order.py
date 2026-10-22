import frappe
from frappe import _

from ffl_manager.compliance.engine import apply, get_rules, get_ship_state


def validate(doc, method=None):
	"""Apply State Compliance Rules to a Work Order's required_items while
	it's still a draft, so quick_complete_work_order (job_card_automation)
	and the standard "Finish" button both consume the substituted parts -
	see _get_pending_transfer/_get_pending_consumption in
	job_card_automation/overrides/work_order.py, which build off
	required_items directly."""
	if doc.docstatus != 0 or not doc.sales_order:
		_clear_compliance_fields(doc)
		return

	state = get_ship_state(doc)
	if not state:
		_clear_compliance_fields(doc)
		return

	rules = get_rules(state, doc.production_item)
	if not rules:
		_clear_compliance_fields(doc)
		return

	changes = apply(doc.required_items, rules)
	_set_compliance_fields(doc, state, changes)


def _clear_compliance_fields(doc):
	if doc.get("custom_restricted_build"):
		doc.custom_restricted_build = 0
	if doc.get("custom_compliance_state"):
		doc.custom_compliance_state = None
	if doc.get("custom_compliance_changes"):
		doc.custom_compliance_changes = None


def _set_compliance_fields(doc, state, changes):
	if not changes:
		_clear_compliance_fields(doc)
		return

	doc.custom_restricted_build = 1
	doc.custom_compliance_state = state
	doc.custom_compliance_changes = _format_changes(changes)


def _format_changes(changes):
	lines = []
	for change in changes:
		if change["action"] == "Replace":
			lines.append(f"{change['from_item']} \u2192 {change['to_item']}")
		elif change["action"] == "Remove":
			lines.append(f"Remove {change['from_item']}")
		elif change["action"] == "Add":
			lines.append(f"Add {change['to_item']}")
	return "; ".join(lines)


def copy_compliance_note_to_job_cards(doc, method=None):
	"""Called after a Work Order's Job Cards exist (on_submit, after
	core's create_job_card runs as part of its own on_submit body - see
	Document.hook's compose(), which calls the original method before any
	doc_events hooks) so the builder sees the same restricted-build note on
	the shop floor, not just on the Work Order form."""
	if not doc.get("custom_restricted_build") or not doc.get("custom_compliance_changes"):
		return

	note = _("RESTRICTED BUILD ({0}): {1}").format(
		doc.custom_compliance_state, doc.custom_compliance_changes
	)

	job_cards = frappe.get_all("Job Card", filters={"work_order": doc.name, "docstatus": ["!=", 2]}, pluck="name")
	for job_card in job_cards:
		frappe.db.set_value("Job Card", job_card, "custom_compliance_note", note, update_modified=False)
