"""Compliance Rework: a draft Repack Stock Entry that converts a
standard-spec part back into the restricted-state substitution, for a
finished good that was built before the order's ship-to state/rules were
known (or was pulled from stock already built to standard spec).

Created via the Delivery Note's "Create Compliance Rework" button
(public/js/delivery_note.js) on a specific Delivery Note Item row.
"""
import frappe
from frappe import _

from ffl_manager.compliance.engine import get_rules, get_ship_state


def _get_substitution_for_item(state, item_code):
	"""The single Replace substitution (from_item -> to_item) that applies
	to `item_code` for `state`. Rework only makes sense for a Replace -
	Remove/Add rules don't name a specific original part on the finished
	good to convert from."""
	rules = get_rules(state, item_code)
	for rule in rules:
		for sub in rule.get("substitutions", []):
			if sub.get("action") == "Replace" and sub.get("from_item") == item_code:
				return sub
	return None


@frappe.whitelist()
def create_compliance_rework(delivery_note, item_row_name):
	"""Build (but do not submit) a Repack Stock Entry that takes the
	restricted-state item back from stock in place of the standard-spec
	item it's replacing, and links it to the Delivery Note Item row so
	compliance_delivery_note.validate_compliance recognizes the rework is
	done once that Stock Entry is submitted.

	Doesn't actually know which specific part needs reworking from the
	Delivery Note alone - that's always the finished-good item code itself
	here, since rework targets a whole built gun (e.g. swap its magazine),
	not a sub-component - so the substitution rule must name the DN line's
	own item_code as its from_item.
	"""
	dn = frappe.get_doc("Delivery Note", delivery_note)
	item_row = next((row for row in dn.items if row.name == item_row_name), None)
	if not item_row:
		frappe.throw(_("Delivery Note Item {0} not found on {1}.").format(item_row_name, delivery_note))

	state = get_ship_state(dn)
	if not state:
		frappe.throw(_("Could not determine a ship-to state for {0}.").format(delivery_note))

	substitution = _get_substitution_for_item(state, item_row.item_code)
	if not substitution:
		frappe.throw(
			_("No Replace substitution found for {0} in {1}. Nothing to rework.").format(
				item_row.item_code, state
			)
		)

	to_item = substitution.get("to_item")
	to_item_details = frappe.db.get_value("Item", to_item, ["item_name", "stock_uom"], as_dict=True)
	if not to_item_details:
		frappe.throw(
			_("Substitution target item {0} does not exist. Fix the State Compliance Rule first.").format(
				to_item
			)
		)

	from_item_details = frappe.db.get_value(
		"Item", item_row.item_code, ["item_name", "stock_uom"], as_dict=True
	)

	warehouse = item_row.warehouse
	if not warehouse:
		frappe.throw(
			_("Row #{0} on {1} has no warehouse set; can't build a rework entry without knowing "
			  "where the stock is.").format(item_row.idx, delivery_note)
		)

	rework = frappe.new_doc("Stock Entry")
	rework.stock_entry_type = "Repack"
	rework.company = dn.company

	rework.append(
		"items",
		{
			"item_code": to_item,
			"item_name": to_item_details.item_name,
			"qty": 1,
			"stock_uom": to_item_details.stock_uom,
			"uom": to_item_details.stock_uom,
			"conversion_factor": 1,
			"s_warehouse": warehouse,
		},
	)
	rework.append(
		"items",
		{
			"item_code": item_row.item_code,
			"item_name": from_item_details.item_name if from_item_details else item_row.item_name,
			"qty": 1,
			"stock_uom": from_item_details.stock_uom if from_item_details else item_row.stock_uom,
			"uom": from_item_details.stock_uom if from_item_details else item_row.stock_uom,
			"conversion_factor": 1,
			"t_warehouse": warehouse,
		},
	)
	rework.insert(ignore_permissions=True)

	frappe.db.set_value("Delivery Note Item", item_row.name, "custom_compliance_rework", rework.name)

	return rework.name
