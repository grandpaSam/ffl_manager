"""Delivery Note before_submit compliance gate.

Runs after ffl_manager's own validate_ffl_required (both are chained on
before_submit in hooks.py; FFL check first since it's the stricter/older
gate - order between hooks within one app's own doc_events list IS
deterministic, read top to bottom - see frappe.append_hook/get_doc_hooks).
"""
import frappe
from frappe import _

from ffl_manager.compliance.engine import get_rules, get_ship_state


def _packed_rows_for(doc, item_row):
	return [row for row in (doc.get("packed_items") or []) if row.parent_detail_docname == item_row.name]


def _is_finished_good(item_code):
	"""True for a manufactured item (has an active BOM) - i.e. a gun built
	at the Work Order, as opposed to a Product Bundle/kit parent item
	(handled via packed_items instead - see compliance_packed_items.py) or
	a plain stocked part."""
	return bool(frappe.db.exists("BOM", {"item": item_code, "is_active": 1}))


def _has_broken_substitution(rows, rules):
	"""True if any row in `rows` still carries an item a rule says should
	have been Replaced/Removed for this state - i.e. the rules were never
	applied (or were reverted) before this Delivery Note tried to submit."""
	for rule in rules:
		for sub in rule.get("substitutions", []):
			if sub.get("action") not in ("Replace", "Remove"):
				continue
			from_item = sub.get("from_item")
			if any(row.item_code == from_item for row in rows):
				return True
	return False


def _has_compliant_work_order(sales_order, item_code):
	return bool(
		frappe.db.exists(
			"Work Order",
			{
				"sales_order": sales_order,
				"production_item": item_code,
				"docstatus": 1,
				"custom_restricted_build": 1,
			},
		)
	)


def _has_submitted_rework(item_row):
	rework = item_row.get("custom_compliance_rework")
	if not rework:
		return False
	return frappe.db.get_value("Stock Entry", rework, "docstatus") == 1


def validate_compliance(doc, method=None):
	if doc.get("custom_skip_ffl_check"):
		# Mirrors validate_ffl_required's own escape hatch (RMA-linked
		# repair returns, etc.) - compliance enforcement doesn't apply to a
		# shipment that's explicitly been marked as not going through the
		# normal sales flow.
		return

	state = get_ship_state(doc)
	if not state:
		return

	blocking = []

	for item in doc.items:
		if not item.item_code:
			continue

		rules = get_rules(state, item.item_code)
		if not rules:
			continue

		packed_rows = _packed_rows_for(doc, item)
		rows_to_check = packed_rows if packed_rows else [item]

		if _has_broken_substitution(rows_to_check, rules):
			blocking.append(
				_("Row #{0}: {1} still has a part that breaks an active State Compliance Rule for {2}.").format(
					item.idx, item.item_code, state
				)
			)
			continue

		if packed_rows:
			# Kit: the swap already happened on packed_items (see
			# compliance_packed_items.py) and was just confirmed above -
			# nothing further to check. The WO-based rework check below is
			# specific to guns built (or not) at the Work Order.
			continue

		if not _is_finished_good(item.item_code):
			continue

		if not item.against_sales_order:
			continue

		if _has_compliant_work_order(item.against_sales_order, item.item_code):
			continue

		if _has_submitted_rework(item):
			continue

		blocking.append(
			_(
				"Row #{0}: {1} was built to standard spec (no restricted-build Work Order found "
				"for this Sales Order) but is shipping to {2}; rework needed. Use the "
				"\"Create Compliance Rework\" button on this row."
			).format(item.idx, item.item_code, state)
		)

	if blocking:
		frappe.throw("<br>".join(blocking), title=_("Restricted State Compliance"))
