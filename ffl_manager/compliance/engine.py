"""State compliance substitution engine.

A "State Compliance Rule" says: for these ship-to states (and optionally one
item group), replace/remove/add these parts. Rules are user-edited (see the
State Compliance Rule doctype) - this module only applies them. It is
deliberately frappe-light where possible (normalize_state, apply, and the
rule-matching predicate are plain functions) so the core logic is unit
testable without a site - see test_engine.py.
"""

import re

import frappe
from frappe import _

RULE_CACHE_KEY = "ffl_manager_compliance_rules::all"

# Fields various child tables use for "which warehouse this row concerns".
# Work Order Item uses source_warehouse, Stock Entry Detail uses
# s_warehouse/t_warehouse, Packed Item uses warehouse/target_warehouse.
# Used by _refresh_warehouse to backfill an empty field on a Replace'd row
# from a sibling row's SAME field (never mixing source-type and
# target-type values on one row).
_WAREHOUSE_FIELDS = ("source_warehouse", "s_warehouse", "warehouse", "t_warehouse", "target_warehouse")

# Subset used when building a brand new row for an Add substitution: a part
# being added is consumed material, so it needs a *source* warehouse, never
# a target/destination one.
_SOURCE_WAREHOUSE_FIELDS = ("source_warehouse", "s_warehouse", "warehouse")

# Linkage fields that identify which top-level line/kit a child row belongs
# to - not item-specific, so a new Add row must inherit them verbatim from
# its siblings (all candidate rows share the same value, since they're
# filtered to one kit/line by the caller - see Packed Item's
# parent_detail_docname/parent_item, used by ffl_manager's own
# validations/compliance_packed_items.py to scope one kit's rows).
_LINK_FIELDS = ("parent_detail_docname", "parent_item")


# ---------------------------------------------------------------------------
# State name/code normalization
# ---------------------------------------------------------------------------

USPS_CODES = {
	"AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
	"HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
	"MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
	"NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
	"SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
	"DC", "PR", "GU", "VI", "AS", "MP",
}

STATE_NAME_TO_CODE = {
	"alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
	"california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
	"florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
	"illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
	"kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
	"massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
	"mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
	"nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
	"new mexico": "NM", "new york": "NY", "north carolina": "NC",
	"north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
	"pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
	"south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
	"vermont": "VT", "virginia": "VA", "washington": "WA",
	"west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
	"district of columbia": "DC", "washington dc": "DC", "washington d.c.": "DC",
	"puerto rico": "PR", "guam": "GU", "virgin islands": "VI",
	"u.s. virgin islands": "VI", "american samoa": "AS",
	"northern mariana islands": "MP",
}


def normalize_state(value):
	"""Standardize free-text state values ("OR", "Ohio", "Tn", "ar", "Texas")
	to a two-letter USPS code. Returns None if it can't be mapped (callers
	that need to surface that, e.g. the one-time address patch, should log
	the original value for a human to fix)."""
	if not value:
		return None

	cleaned = re.sub(r"\s+", " ", value).strip()
	if not cleaned:
		return None

	if len(cleaned) == 2 and cleaned.upper() in USPS_CODES:
		return cleaned.upper()

	return STATE_NAME_TO_CODE.get(cleaned.lower())


# ---------------------------------------------------------------------------
# Ship-to state resolution
# ---------------------------------------------------------------------------


def _doc_get(doc, field):
	getter = getattr(doc, "get", None)
	if callable(getter):
		return getter(field)
	return getattr(doc, field, None)


def _resolve_sales_order(doc):
	"""The Sales Order behind `doc`, if any - direct (Sales Order itself,
	Work Order.sales_order) or one hop via Work Order (Stock Entry.work_order)."""
	if doc.doctype == "Sales Order":
		return doc.name

	sales_order = _doc_get(doc, "sales_order")
	if sales_order:
		return sales_order

	work_order = _doc_get(doc, "work_order")
	if work_order:
		return frappe.db.get_value("Work Order", work_order, "sales_order")

	return None


def get_ship_state(doc):
	"""Normalized USPS ship-to state for `doc`. Reads doc's own
	shipping_address_name if it has one (Sales Order, Delivery Note),
	otherwise falls back to the shipping address of the Sales Order linked
	to it (Work Order, Stock Entry via its Work Order)."""
	address_name = _doc_get(doc, "shipping_address_name")

	if not address_name:
		sales_order = _resolve_sales_order(doc)
		if sales_order:
			address_name = frappe.db.get_value("Sales Order", sales_order, "shipping_address_name")

	if not address_name:
		return None

	state = frappe.db.get_value("Address", address_name, "state")
	return normalize_state(state)


# ---------------------------------------------------------------------------
# Rule lookup
# ---------------------------------------------------------------------------


def clear_rule_cache():
	frappe.cache.delete_value(RULE_CACHE_KEY)


def _load_all_rules():
	"""Every State Compliance Rule, enabled or not - filtering happens in
	_rule_applies so the cache is reusable across any state/item combo."""
	rules = []
	for name in frappe.get_all("State Compliance Rule", pluck="name"):
		doc = frappe.get_doc("State Compliance Rule", name)
		rules.append(
			{
				"name": doc.name,
				"rule_name": doc.rule_name,
				"enabled": bool(doc.enabled),
				"states": [row.state for row in doc.states],
				"applies_to_item_group": doc.applies_to_item_group,
				"substitutions": [
					{
						"action": row.action,
						"from_item": row.from_item,
						"to_item": row.to_item,
						"qty": row.qty,
					}
					for row in doc.substitutions
				],
			}
		)
	return rules


def _rule_applies(rule, state, item_group=None):
	"""Pure predicate - whether `rule` (a dict shaped like one entry from
	_load_all_rules) applies to `state` and (if given) `item_group`."""
	if not rule.get("enabled"):
		return False
	if state not in (rule.get("states") or []):
		return False

	applies_to = rule.get("applies_to_item_group")
	if applies_to and applies_to != item_group:
		return False

	return True


def get_rules(state, item_code=None):
	"""Enabled State Compliance Rules applicable to `state`, optionally
	narrowed to rules that either have no applies_to_item_group or match
	item_code's item group. Rule data is cached (see clear_rule_cache,
	called whenever a State Compliance Rule is saved/deleted)."""
	if not state:
		return []

	all_rules = frappe.cache.get_value(RULE_CACHE_KEY, generator=_load_all_rules)

	item_group = frappe.db.get_value("Item", item_code, "item_group") if item_code else None
	return [rule for rule in all_rules if _rule_applies(rule, state, item_group)]


# ---------------------------------------------------------------------------
# Applying substitutions to a child table
# ---------------------------------------------------------------------------


def _row_get(row, field, default=None):
	if isinstance(row, dict):
		return row.get(field, default)
	return getattr(row, field, default)


def _row_set(row, field, value):
	if isinstance(row, dict):
		row[field] = value
	else:
		setattr(row, field, value)


def _row_has(row, field):
	if isinstance(row, dict):
		return field in row
	return hasattr(row, field)


def _get_item_or_throw(item_code, rule_name=None):
	item = frappe.db.get_value("Item", item_code, ["item_name", "description", "stock_uom"], as_dict=True)
	if not item:
		frappe.throw(
			_(
				"State Compliance Rule {0} points at item {1}, which does not exist. "
				"Fix the rule before it can be applied."
			).format(frappe.bold(rule_name or ""), frappe.bold(item_code))
		)
	return item


def _first_matching_value(rows, field):
	"""First non-empty value of `field` among `rows` - used to backfill a
	row's own empty field from a sibling row, never mixing different
	fields (e.g. a Work Order Item's source_warehouse never leaks into a
	Stock Entry Detail's t_warehouse; a Packed Item's parent_detail_docname
	never leaks into parent_item)."""
	for row in rows:
		if _row_has(row, field):
			value = _row_get(row, field)
			if value:
				return value
	return None


def _refresh_item_fields(row, item):
	_row_set(row, "item_name", item.item_name)
	if item.description:
		_row_set(row, "description", item.description)

	# Work Order Item only has stock_uom; Stock Entry Detail and Packed Item
	# have both uom and stock_uom (with a conversion_factor between them).
	# Substituted parts are assumed to share the same stock UOM family as
	# the rest of this domain's items (ASRX-XPKG-* mags, grips, etc. are all
	# "Each"), so both get set to the new item's stock_uom and the
	# conversion factor resets to 1 - if that assumption is ever wrong for
	# a future part, the Work Order/Stock Entry form still shows the row for
	# the builder to catch and correct before submitting.
	if _row_has(row, "stock_uom"):
		_row_set(row, "stock_uom", item.stock_uom)
	if _row_has(row, "uom"):
		_row_set(row, "uom", item.stock_uom)
	if _row_has(row, "conversion_factor"):
		_row_set(row, "conversion_factor", 1)


def _refresh_warehouse(row, sibling_rows):
	"""Backfill any of row's own (empty) warehouse fields from a sibling
	row's SAME field - e.g. a new source_warehouse comes from another row's
	source_warehouse, never from a different row's t_warehouse."""
	for field in _WAREHOUSE_FIELDS:
		if _row_has(row, field) and not _row_get(row, field):
			default = _first_matching_value(sibling_rows, field)
			if default:
				_row_set(row, field, default)


def _build_new_row(existing_rows, to_item, qty, rule_name=None):
	item = _get_item_or_throw(to_item, rule_name)
	row = {"item_code": to_item, "item_name": item.item_name, "qty": qty or 1}
	if item.description:
		row["description"] = item.description

	if any(_row_has(r, "stock_uom") for r in existing_rows):
		row["stock_uom"] = item.stock_uom
	if any(_row_has(r, "uom") for r in existing_rows):
		row["uom"] = item.stock_uom
	if any(_row_has(r, "conversion_factor") for r in existing_rows):
		row["conversion_factor"] = 1

	for field in _SOURCE_WAREHOUSE_FIELDS:
		if any(_row_has(r, field) for r in existing_rows):
			default = _first_matching_value(existing_rows, field)
			if default:
				row[field] = default
			break

	for field in _LINK_FIELDS:
		if any(_row_has(r, field) for r in existing_rows):
			default = _first_matching_value(existing_rows, field)
			if default:
				row[field] = default

	return row


def _get_parent_context(rows):
	"""(parent_doc, parentfield) from any row still carrying them (set by
	frappe's own Document.append - see base_document.py's _init_child),
	so newly added rows and the final rebuilt table go through the parent's
	real append() instead of being left as disconnected dicts. Returns
	(None, None) for plain-dict rows (unit tests)."""
	for row in rows:
		parent_doc = getattr(row, "parent_doc", None)
		parentfield = getattr(row, "parentfield", None)
		if parent_doc is not None and parentfield:
			return parent_doc, parentfield
	return None, None


def apply(rows, rules, row_filter=None):
	"""Apply Replace/Remove/Add substitutions from `rules` (as returned by
	get_rules) to `rows`.

	`rows` must be the actual child table list on the document being
	changed (e.g. doc.required_items, doc.items, doc.packed_items) - not a
	filtered copy - because an Add substitution needs to append a real
	child Document onto that exact table (see _get_parent_context) and a
	Remove needs to drop a row from it; a plain list of dicts also works
	(see test_engine.py), just without that document-table handling.

	`row_filter`, if given, restricts which of `rows` Replace/Remove will
	match against and which rows inform a new Add row's uom/warehouse -
	e.g. a Stock Entry's `items` table also holds incoming/finished-good
	rows that substitutions must never touch; pass a filter selecting only
	the outgoing raw-material rows. Rows outside the filter are left
	untouched and still present afterwards.

	Mutates `rows` in place (so callers holding the same list object, e.g.
	doc.required_items, see the result immediately) and returns a list of
	change dicts describing what happened, e.g.:
		{"rule": "WA Mag Swap", "action": "Replace",
		 "from_item": "ASRX-XPKG-9MM-EXT", "to_item": "ASRX-XPKG-9MM-STN"}

	Raises frappe.ValidationError if a substitution's to_item doesn't exist.
	"""
	changes = []
	new_rows = list(rows)

	def _candidates():
		return [r for r in new_rows if row_filter is None or row_filter(r)]

	for rule in rules:
		rule_name = rule.get("rule_name") or rule.get("name")

		for sub in rule.get("substitutions", []):
			action = sub.get("action")
			from_item = sub.get("from_item")
			to_item = sub.get("to_item")

			if action == "Replace":
				matched = [r for r in _candidates() if _row_get(r, "item_code") == from_item]
				if not matched:
					continue
				item = _get_item_or_throw(to_item, rule_name)
				for row in matched:
					_row_set(row, "item_code", to_item)
					_refresh_item_fields(row, item)
					_refresh_warehouse(row, _candidates())
				changes.append(
					{"rule": rule_name, "action": "Replace", "from_item": from_item, "to_item": to_item}
				)

			elif action == "Remove":
				matched = [r for r in _candidates() if _row_get(r, "item_code") == from_item]
				if not matched:
					continue
				new_rows = [r for r in new_rows if r not in matched]
				changes.append({"rule": rule_name, "action": "Remove", "from_item": from_item})

			elif action == "Add":
				new_row = _build_new_row(_candidates(), to_item, sub.get("qty"), rule_name)
				new_rows.append(new_row)
				changes.append({"rule": rule_name, "action": "Add", "to_item": to_item})

	if changes:
		parent_doc, parentfield = _get_parent_context(rows)
		if parent_doc is not None:
			# Rebuild in place: clear() empties the same underlying list
			# object `rows` (== doc.__dict__[parentfield]), so append()
			# below - which looks that table up fresh via self.__dict__ each
			# call - writes back into it rather than into some other list
			# doc.required_items would stop pointing at. Existing rows are
			# already Document instances, so append() (_init_child) reuses
			# them as-is (keeping their name); only the plain dicts built by
			# _build_new_row become newly-created child Documents here.
			# idx is renumbered afterwards (append() only assigns a fresh
			# idx to rows that don't already have one, which would leave
			# gaps if a Remove dropped a row from the middle).
			rows.clear()
			for row in new_rows:
				parent_doc.append(parentfield, row)
			for i, row in enumerate(rows, 1):
				row.idx = i
		else:
			rows[:] = new_rows

	return changes
