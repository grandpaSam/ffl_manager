from ffl_manager.compliance.engine import normalize_state


def validate(doc, method=None):
	"""Standardize Address.state to a USPS code for US addresses, so
	get_ship_state's lookups (and the one-time patches/normalize_us_address_
	states patch, for existing data) always see a clean value.

	Scoped to country == "United States" only - this app has no opinion on
	what a province/region string should look like for any other country,
	and normalize_state's US-only name map would otherwise mangle
	non-US values that happen to collide with a US state name/code.
	"""
	if doc.country != "United States" or not doc.state:
		return

	normalized = normalize_state(doc.state)
	if normalized:
		doc.state = normalized
