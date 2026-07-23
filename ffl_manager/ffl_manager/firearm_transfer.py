# Copyright (c) 2026, Chiron Interactive and contributors
# For license information, please see license.txt
import frappe
from frappe import _


def parse_serial_nos(serial_no_text):
	return [s.strip() for s in (serial_no_text or "").split("\n") if s.strip()]


def determine_firearm_type(item_name):
	name = (item_name or "").lower()
	if "pistol" in name:
		return "Pistol"
	if "rifle" in name:
		return "Rifle"
	frappe.throw(
		_(
			'Could not determine firearm type (Rifle/Pistol) from item name "{0}". '
			"Fix the item name or record this transfer manually in the Firearm Transfer Log."
		).format(item_name)
	)


def get_default_make():
	make = frappe.db.get_single_value("FFL Manager Settings", "default_make")
	if not make:
		frappe.throw(_("Please set a Default Make in FFL Manager Settings before shipping or receiving firearms."))
	return make


def create_transfer_log_entry(
	direction,
	transfer_date,
	firearm_type,
	serial_no,
	source_doctype,
	source_docname,
	sales_order=None,
	rma=None,
	received_from_address=None,
	sent_to_address=None,
	ffl_license_number=None,
	ffl_company_name=None,
	recipient_name=None,
):
	if frappe.db.exists(
		"Firearm Transfer Log",
		{
			"source_doctype": source_doctype,
			"source_docname": source_docname,
			"serial_number": serial_no,
		},
	):
		return

	doc = frappe.new_doc("Firearm Transfer Log")
	doc.update(
		{
			"direction": direction,
			"transfer_date": transfer_date,
			"serial_number": serial_no,
			"make": get_default_make(),
			"model": "ASR",
			"firearm_type": firearm_type,
			"auto_generated": 1,
			"source_doctype": source_doctype,
			"source_docname": source_docname,
			"sales_order": sales_order,
			"rma": rma,
			"received_from_address": received_from_address,
			"sent_to_address": sent_to_address,
			"ffl_license_number": ffl_license_number,
			"ffl_company_name": ffl_company_name,
			"recipient_name": recipient_name,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc
