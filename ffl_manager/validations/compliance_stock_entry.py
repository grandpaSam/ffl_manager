import frappe

from ffl_manager.compliance.engine import apply, get_rules, get_ship_state

_CONSUMPTION_PURPOSES = {"Manufacture", "Material Transfer for Manufacture"}


def _is_outgoing_row(row):
	"""True for a raw-material (consumed) row - has a source warehouse and
	no target warehouse. Excludes incoming/finished-good rows (e.g. the
	Manufacture entry's finished item, which has t_warehouse set) so
	substitutions never touch them. Works for both real Stock Entry Detail
	Documents and plain dicts (defensive, though this hook always sees
	real rows)."""
	s_warehouse = row.get("s_warehouse") if isinstance(row, dict) else getattr(row, "s_warehouse", None)
	t_warehouse = row.get("t_warehouse") if isinstance(row, dict) else getattr(row, "t_warehouse", None)
	return bool(s_warehouse) and not t_warehouse


def validate(doc, method=None):
	"""Re-apply the linked Work Order's State Compliance Rules to the
	outgoing (raw material) rows of a Manufacture or Material Transfer for
	Manufacture Stock Entry.

	Manufacturing Settings on this site has
	backflush_raw_materials_based_on = BOM, so ERPNext's standard "Finish"
	button re-reads the BOM for the Manufacture entry's outgoing rows
	instead of reusing whatever the Work Order's required_items ended up
	with - meaning the Work Order validate hook's substitution (see
	validations/work_order.py) doesn't automatically carry through to a
	plain "Finish" click the way it does for quick_complete_work_order
	(which builds its Stock Entries directly from required_items). This
	hook re-applies the same rules here so both paths agree.
	"""
	if doc.docstatus != 0 or doc.purpose not in _CONSUMPTION_PURPOSES or not doc.work_order:
		return

	work_order = frappe.db.get_value(
		"Work Order", doc.work_order, ["sales_order", "production_item"], as_dict=True
	)
	if not work_order or not work_order.sales_order:
		return

	state = get_ship_state(doc)
	if not state:
		return

	rules = get_rules(state, work_order.production_item)
	if not rules:
		return

	apply(doc.items, rules, row_filter=_is_outgoing_row)
