"""Client for ATF's FFL eZ Check (https://fflezcheck.atf.gov/).

eZ Check is searched by the first 3 and last 5 digits of a license only and
masks the middle (9-12-XXX-XX-XX-67890), so it can't confirm county or type -
but its expiration date pins down the 5th segment (ocr.expiration_segment).
No API: accept the warning banner for a session cookie, POST the search form,
and read the results table by its labels.
"""

import datetime
import re

BASE_URL = "https://fflezcheck.atf.gov/FFLEzCheck"
TIMEOUT = 20


class EzCheckError(Exception):
	"""eZ Check couldn't be reached or returned something unparseable."""


class LicenseNotFound(EzCheckError):
	"""ATF has no license with that region/district/sequence."""


def lookup(region, district, sequence, session=None):
	"""Search eZ Check. Returns parse_result()'s dict; raises EzCheckError."""
	import requests

	session = session or requests.Session()
	session.headers.setdefault("User-Agent", "Mozilla/5.0 (ffl_manager)")
	try:
		session.get(f"{BASE_URL}/fflSearch.action", params={"warning_banner_accept": "true"}, timeout=TIMEOUT)
		response = session.post(
			f"{BASE_URL}/fflSearch",
			data={"licsRegn": region, "licsDis": district, "licsSeq": sequence},
			timeout=TIMEOUT,
		)
		response.raise_for_status()
	except requests.RequestException as e:
		raise EzCheckError(f"Could not reach ATF FFL eZ Check: {e}")

	return parse_result(response.text)


def _cell_lines(cell):
	return [line.strip() for line in cell.get_text("\n").splitlines() if line.strip()]


def parse_result(html):
	"""Read an eZ Check results page.

	Returns {"masked_license_number", "expiration_date" (date), "license_name",
	"trade_name", "premise_address": {address_line1, address_line2, city,
	state, pincode}, "loa_issue_date", "loa_expiration_date"}.
	"""
	from bs4 import BeautifulSoup

	soup = BeautifulSoup(html, "html.parser")
	fields = {}
	for row in soup.find_all("tr"):
		cells = row.find_all("td", recursive=False)
		if len(cells) != 2:
			continue
		label = cells[0].get_text(" ", strip=True).rstrip(": ").strip()
		if label and label not in fields:
			fields[label] = _cell_lines(cells[1])

	if "License Number" not in fields:
		if "possibility that the FFL you are attempting to verify is invalid" in soup.get_text(" "):
			raise LicenseNotFound("ATF has no license matching that number.")
		raise EzCheckError("Unrecognized response from ATF FFL eZ Check.")

	def first(label):
		lines = fields.get(label) or []
		return lines[0] if lines else ""

	try:
		value = first("Expiration Date")
		expiration = datetime.datetime.strptime(value, "%m/%d/%Y").date() if value else None
	except ValueError:
		raise EzCheckError(f"Unrecognized expiration date from ATF: {first('Expiration Date')!r}")
	if not expiration:
		raise EzCheckError("ATF returned no expiration date.")

	return {
		"masked_license_number": first("License Number"),
		"expiration_date": expiration,
		"license_name": first("License Name"),
		"trade_name": first("Trade Name"),
		"premise_address": parse_address(fields.get("Premise Address") or []),
		"loa_issue_date": _optional_date(first("LOA Issue Date")),
		"loa_expiration_date": _optional_date(first("LOA Expiration Date")),
	}


def _optional_date(value):
	try:
		return datetime.datetime.strptime(value, "%m/%d/%Y").date() if value else None
	except ValueError:
		return None


def parse_address(lines):
	"""["1200 SAMPLE CANYON ROAD", "FAIRVIEW", "CO - 80999"] -> Address fields."""
	if len(lines) < 3:
		raise EzCheckError(f"Unrecognized premise address from ATF: {lines!r}")
	m = re.fullmatch(r"([A-Z]{2})\s*-?\s*(\d{5}(?:-?\d{4})?)?", lines[-1].strip())
	if not m:
		raise EzCheckError(f"Unrecognized premise address from ATF: {lines!r}")
	street = lines[:-2]
	return {
		"address_line1": street[0],
		"address_line2": " ".join(street[1:]),
		"city": lines[-2],
		"state": m.group(1),
		"pincode": m.group(2) or "",
	}
