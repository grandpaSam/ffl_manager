"""Create or update an FFL Dealer from an uploaded copy of its license.

The client drives three steps (public/js/ffl_import.js):
  1. read_ffl_copy  - OCR the copy; the user confirms/corrects the number
  2. verify_ffl     - look it up on ATF eZ Check; the user reviews the changes
  3. apply_ffl_copy - re-verify and write the dealer, its premise address and copy

apply_ffl_copy repeats the ATF lookup rather than trusting what the client
sends back, so everything but the license number, signee and (for a new
dealer) its name comes from ATF.
"""

import re
import string

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, today

from ffl_manager.ffl_lookup import ezcheck, ocr

_KEEP_UPPER = {"LLC", "INC", "LTD", "LP", "LLP", "PC", "PLLC", "USA", "II", "III", "IV", "NE", "NW", "SE", "SW", "PO"}


def _title(value):
	"""ATF data is all caps: "MESA RIDGE ARMORY LLC" -> "Mesa Ridge Armory LLC"."""
	return " ".join(w if w in _KEEP_UPPER else string.capwords(w) for w in (value or "").split())


def _get_file(file_url):
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		frappe.throw(_("File {0} not found").format(file_url))
	file = frappe.get_doc("File", name)
	file.check_permission("read")
	return file


def _split_license(license_number):
	"""Validate a confirmed number into its six segments.

	The 5th (expiration) segment isn't validated: verify_ffl rebuilds it from
	ATF's expiration date.
	"""
	segments = [s.strip().upper() for s in re.split(r"[-\s]+", (license_number or "").strip())]
	pattern = (r"\d", r"\d{2}", r"\d{3}", r"\d{2}", r".*", r"\d{5}")
	if len(segments) != 6 or not all(re.fullmatch(p, s) for p, s in zip(pattern, segments)):
		frappe.throw(_("{0} is not a valid FFL number (expected e.g. 9-12-345-01-8K-67890)").format(license_number))
	return segments


def _find_dealers(segments):
	"""Dealers holding this license. ATF identifies a license by region,
	district and sequence; the expiration segment changes on renewal."""
	pattern = f"{segments[0]}-{segments[1]}-%-{segments[5]}"
	return frappe.get_all("FFL Dealer", filters={"license_number": ["like", pattern]}, pluck="name")


def _premise_address_name(dealer):
	return frappe.db.get_value(
		"Address",
		filters=[
			["Dynamic Link", "link_doctype", "=", "FFL Dealer"],
			["Dynamic Link", "link_name", "=", dealer],
			["Dynamic Link", "parenttype", "=", "Address"],
			["disabled", "=", 0],
		],
		fieldname="name",
		order_by="is_primary_address desc, creation asc",
	)


def _address_fields(address):
	return {
		"address_line1": _title(address["address_line1"]),
		"address_line2": _title(address["address_line2"]),
		"city": _title(address["city"]),
		"state": address["state"],
		"pincode": address["pincode"],
		"country": "United States",
	}


def _same_address(a, b):
	def key(addr):
		return (
			re.sub(r"\W", "", f"{addr.get('address_line1') or ''}{addr.get('address_line2') or ''}").lower(),
			(addr.get("pincode") or "")[:5],
		)

	return key(a) == key(b)


def _unique_dealer_name(name):
	candidate, n = name, 1
	while frappe.db.exists("FFL Dealer", candidate):
		n += 1
		candidate = f"{name} ({n})"
	return candidate


def _verify(license_number, dealer=None, ocr_expiration_date=None, ocr_license_type=None):
	segments = _split_license(license_number)
	try:
		atf = ezcheck.lookup(segments[0], segments[1], segments[5])
	except ezcheck.LicenseNotFound:
		frappe.throw(
			_(
				"ATF has no license {0}-{1}-XXX-XX-XX-{2}. Check the number; if it is right, the license may be "
				"invalid - do not complete a transfer without contacting ATF (1-877-560-2435)."
			).format(segments[0], segments[1], segments[5]),
			title=_("License Not Found"),
		)
	except ezcheck.EzCheckError as e:
		frappe.throw(str(e), title=_("ATF eZ Check Unavailable"))

	warnings = []
	expiration_segment = ocr.expiration_segment(atf["expiration_date"])
	if segments[4] != expiration_segment:
		warnings.append(
			_("Expiration segment corrected from {0} to {1} to match ATF's expiration date.").format(
				segments[4] or "(blank)", expiration_segment
			)
		)
		segments[4] = expiration_segment
	license_number = "-".join(segments)

	if atf["expiration_date"] < getdate(today()):
		warnings.append(_("ATF shows this license EXPIRED on {0}.").format(frappe.format(atf["expiration_date"], "Date")))
	if atf["loa_expiration_date"]:
		warnings.append(
			_("Renewal pending: ATF Letter of Authorization valid until {0}.").format(
				frappe.format(atf["loa_expiration_date"], "Date")
			)
		)
	if ocr_expiration_date and getdate(ocr_expiration_date) != atf["expiration_date"]:
		warnings.append(
			_("The copy shows expiration {0} but ATF shows {1} - this may be an outdated copy.").format(
				frappe.format(getdate(ocr_expiration_date), "Date"), frappe.format(atf["expiration_date"], "Date")
			)
		)
	if segments[3] not in ocr.LICENSE_TYPES:
		warnings.append(_("License type {0} is not a known FFL type - check the 4th segment.").format(segments[3]))
	elif ocr_license_type and ocr_license_type != segments[3]:
		warnings.append(
			_("The copy's Type of License reads {0} but the number says {1} - check the 4th segment.").format(
				ocr_license_type, segments[3]
			)
		)

	matches = _find_dealers(segments)
	if dealer:
		frappe.has_permission("FFL Dealer", "write", dealer, throw=True)
		others = [m for m in matches if m != dealer]
		if others:
			warnings.append(_("This license is also on file as {0}.").format(", ".join(others)))
		current_number = frappe.db.get_value("FFL Dealer", dealer, "license_number") or ""
		if current_number and dealer not in matches:
			warnings.append(_("This copy is for a different license than {0}'s current one ({1}).").format(dealer, current_number))
	elif matches:
		dealer = matches[0]
		if len(matches) > 1:
			warnings.append(_("This license is on file more than once ({0}); updating {1}.").format(", ".join(matches), dealer))

	premise = _address_fields(atf["premise_address"])
	current = None
	if dealer:
		doc = frappe.get_doc("FFL Dealer", dealer)
		address_name = _premise_address_name(dealer)
		address = frappe.db.get_value("Address", address_name, list(premise), as_dict=True) if address_name else None
		current = {
			"dealer_name": doc.dealer_name,
			"license_number": doc.license_number,
			"expiration_date": doc.expiration_date,
			"license_name": doc.license_name,
			"trade_name": doc.trade_name,
			"license_type": doc.license_type,
			"signee_name": doc.signee_name,
			"ffl_copy": doc.ffl_copy,
			"address_name": address_name,
			"address": address,
			"address_changes": not address or not _same_address(address, premise),
		}

	return {
		"license_number": license_number,
		"segments": segments,
		"expiration_date": atf["expiration_date"],
		"license_name": _title(atf["license_name"]),
		"trade_name": _title(atf["trade_name"]),
		"license_type": f"{segments[3]} - {ocr.LICENSE_TYPES.get(segments[3], _('Unknown'))}",
		"premise_address": premise,
		"loa_expiration_date": atf["loa_expiration_date"],
		"dealer": dealer,
		"current": current,
		"suggested_dealer_name": None
		if dealer
		else _unique_dealer_name(_title(atf["trade_name"] or atf["license_name"])),
		"warnings": warnings,
	}


@frappe.whitelist()
def read_ffl_copy(file_url):
	frappe.has_permission("FFL Dealer", "write", throw=True)
	file = _get_file(file_url)
	try:
		result = ocr.extract_ffl_data(file.get_full_path())
	except Exception:
		frappe.log_error(title="FFL copy OCR failed")
		frappe.throw(_("Could not read {0}. Make sure it is a PDF or image of an FFL.").format(file.file_name))
	if result["license"]:
		result["license"].pop("score", None)
	return result


@frappe.whitelist()
def verify_ffl(license_number, dealer=None, ocr_expiration_date=None, ocr_license_type=None):
	frappe.has_permission("FFL Dealer", "write" if dealer else "create", throw=True)
	return _verify(license_number, dealer, ocr_expiration_date, ocr_license_type)


@frappe.whitelist()
def apply_ffl_copy(file_url, license_number, dealer=None, dealer_name=None, signee_name=None):
	"""Create or update the dealer. Returns the dealer's name."""
	file = _get_file(file_url)
	result = _verify(license_number, dealer)
	dealer = result["dealer"]

	if dealer:
		doc = frappe.get_doc("FFL Dealer", dealer)
		doc.check_permission("write")
		if doc.ffl_copy and doc.ffl_copy != file.file_url:
			doc.append(
				"previous_copies",
				{
					"ffl_copy": doc.ffl_copy,
					"expiration_date": doc.expiration_date,
					"archived_on": today(),
					"notes": _("Replaced by FFL copy import ({0})").format(result["license_number"]),
				},
			)
	else:
		dealer_name = (dealer_name or "").strip() or result["suggested_dealer_name"]
		if frappe.db.exists("FFL Dealer", dealer_name):
			frappe.throw(_("An FFL Dealer named {0} already exists").format(dealer_name))
		doc = frappe.new_doc("FFL Dealer")
		doc.dealer_name = dealer_name

	doc.update(
		{
			"license_number": result["license_number"],
			"expiration_date": result["expiration_date"],
			"license_name": result["license_name"],
			"trade_name": result["trade_name"],
			"license_type": result["license_type"],
			"atf_verified_on": now_datetime(),
			"ffl_copy": file.file_url,
		}
	)
	if (signee_name or "").strip():
		doc.signee_name = signee_name.strip()
	doc.save()

	if not file.attached_to_doctype:
		file.db_set({"attached_to_doctype": "FFL Dealer", "attached_to_name": doc.name, "attached_to_field": "ffl_copy"})

	_set_premise_address(doc.name, result["premise_address"], (result["current"] or {}).get("address_name"))
	return doc.name


def _set_premise_address(dealer, premise, current_name):
	"""Make ATF's premise address the dealer's primary shipping address.

	A changed address becomes a new Address (Frappe un-sets primary/shipping on
	the old one) rather than an edit, so the old one stays as it was.
	"""
	if current_name:
		current = frappe.get_doc("Address", current_name)
		if _same_address(current.as_dict(), premise):
			if not (current.is_primary_address and current.is_shipping_address):
				current.is_primary_address = current.is_shipping_address = 1
				current.save()
			return

	frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": dealer,
			"address_type": "Shipping",
			**premise,
			"is_primary_address": 1,
			"is_shipping_address": 1,
			"links": [{"link_doctype": "FFL Dealer", "link_name": dealer}],
		}
	).insert()
