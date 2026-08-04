# Copyright (c) 2026, Chiron Interactive and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.contacts.doctype.address.address import get_address_display
from frappe.model.document import Document
from frappe.utils import strip_html


class FirearmTransferLog(Document):
	pass


@frappe.whitelist()
def fetch_from_sales_order(sales_order):
	from ffl_manager.ffl_manager.doctype.ffl_dealer.ffl_dealer import get_dealer_address_display

	so = frappe.db.get_value(
		"Sales Order",
		sales_order,
		["custom_ffl_dealer", "shipping_address", "address_display"],
		as_dict=True,
	)
	if not so:
		frappe.throw(_("Sales Order {0} not found").format(sales_order))

	result = {
		"ffl_license_number": "",
		"ffl_company_name": "",
	}

	if so.custom_ffl_dealer:
		# Firearms requiring an FFL must ship to the dealer's premises, not the customer's address.
		result["sent_to_address"] = get_dealer_address_display(so.custom_ffl_dealer) or ""

		dealer = frappe.db.get_value(
			"FFL Dealer", so.custom_ffl_dealer, ["license_number", "dealer_name"], as_dict=True
		)
		if dealer:
			result["ffl_license_number"] = dealer.license_number
			result["ffl_company_name"] = dealer.dealer_name
	else:
		result["sent_to_address"] = strip_html(so.shipping_address or so.address_display or "")

	return result


@frappe.whitelist()
def get_caliber_mapping():
	"""Caliber (as typed on this doctype) -> legacy FileMaker caliber string, for the Copy to Clipboard button."""
	rows = frappe.get_single("FFL Manager Settings").caliber_mapping
	return {row.caliber.lower(): row.filemaker_caliber for row in rows if row.caliber}


@frappe.whitelist()
def fetch_from_rma(rma):
	rma_customer_address = frappe.db.get_value("RMA", rma, "customer_address")
	if rma_customer_address is None:
		frappe.throw(_("RMA {0} not found").format(rma))

	result = {
		"received_from_address": strip_html(get_address_display(rma_customer_address) or "") if rma_customer_address else "",
	}

	serials = [
		d.serial_no
		for d in frappe.get_all(
			"RMA Item", filters={"parent": rma, "parenttype": "RMA"}, fields=["serial_no"]
		)
		if d.serial_no
	]
	if len(serials) == 1:
		result["serial_number"] = serials[0]

	return result