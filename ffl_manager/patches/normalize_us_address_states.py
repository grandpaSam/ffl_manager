"""One-time cleanup of existing US Address.state free-text values ("OR",
"Ohio", "Tn", "ar", "Texas", ...) into USPS codes, so get_ship_state's state
lookups work against clean data from day one. Anything it can't map is left
untouched and printed so a human can fix it (and going forward,
ffl_manager's own Address validate hook - see
validations/compliance_address.py - normalizes new/edited addresses
automatically, so this patch should only ever need to run once).
"""
import frappe

from ffl_manager.compliance.engine import normalize_state


def execute():
	addresses = frappe.get_all(
		"Address",
		filters={"country": "United States", "state": ["is", "set"]},
		fields=["name", "state"],
	)

	updated = 0
	unmapped = []

	for address in addresses:
		normalized = normalize_state(address.state)
		if normalized:
			if normalized != address.state:
				frappe.db.set_value("Address", address.name, "state", normalized, update_modified=False)
				updated += 1
		else:
			unmapped.append((address.name, address.state))

	print(f"normalize_us_address_states: updated {updated} address(es).")
	if unmapped:
		print(f"normalize_us_address_states: could not map {len(unmapped)} address(es), left untouched:")
		for name, state in unmapped:
			print(f"  {name}: {state!r}")
