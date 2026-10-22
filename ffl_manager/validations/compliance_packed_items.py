import frappe

from erpnext.stock.doctype.packed_item.packed_item import get_product_bundle_items

from ffl_manager.compliance.engine import apply, get_rules, get_ship_state


def _packed_rows_for(doc, item_row):
	return [row for row in (doc.get("packed_items") or []) if row.parent_detail_docname == item_row.name]


def _drop_stale_substituted_rows(doc, item_row, packed_rows):
	"""Remove leftover rows from a PREVIOUS save's substitution before
	applying rules again.

	Core's own make_packing_list (erpnext.stock.doctype.packed_item.
	packed_item) rebuilds packed_items on every validate() by looking up
	each existing row by (kit item, ORIGINAL bundle component item_code,
	line) - so once a Replace substitution here mutates a row's item_code
	away from that original component, the next save's make_packing_list
	can't find a match for the original component anymore and appends a
	BRAND NEW pristine row for it, while our already-substituted row is
	left in place untouched. Without this cleanup, every subsequent save
	of an already-compliant Sales Order/Delivery Note would accumulate one
	extra duplicate row per save.

	Any packed row whose item_code isn't one of the kit's current pristine
	component codes is, by construction, something a PRIOR run of this
	hook put there - safe to drop and let get_rules/apply re-derive from
	this save's fresh pristine row(s) instead.
	"""
	pristine_codes = {c.item_code for c in get_product_bundle_items(item_row.item_code)}
	stale = [row for row in packed_rows if row.item_code not in pristine_codes]
	if not stale:
		return packed_rows

	for row in stale:
		doc.remove(row)

	return [row for row in packed_rows if row not in stale]


def validate_packed_items(doc, method=None):
	"""Apply State Compliance Rules to a Sales Order's or Delivery Note's
	packed_items (Product Bundle components), per top-level item row - so
	a rule's optional applies_to_item_group is checked against the KIT's
	own item group, and a substitution only touches that kit's own
	component rows, not another line's.

	Hooked to before_save/before_submit rather than validate: both
	bundle_manager's own Sales Order validate hook (which may create the
	Product Bundle on a first-ever save) and core's own validate() (which
	builds packed_items from whatever Product Bundle already exists) must
	have already run - before_save/before_submit fires strictly after
	EVERY app's validate hook finishes (see
	Document.run_before_save_methods), so this doesn't depend on app
	install order the way two hooks on the same "validate" event would.
	"""
	state = get_ship_state(doc)
	if not state:
		return

	for item_row in doc.items:
		if not item_row.item_code:
			continue
		packed_rows = _packed_rows_for(doc, item_row)
		if not packed_rows:
			continue

		packed_rows = _drop_stale_substituted_rows(doc, item_row, packed_rows)
		if not packed_rows:
			continue

		rules = get_rules(state, item_row.item_code)
		if not rules:
			continue

		apply(
			doc.packed_items,
			rules,
			row_filter=lambda row, _name=item_row.name: row.parent_detail_docname == _name,
		)
