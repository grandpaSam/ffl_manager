import frappe
from frappe import _
from frappe.contacts.doctype.address.address import get_address_display
from frappe.utils import strip_html

from ffl_manager.ffl_manager.firearm_transfer import (
	already_logged,
	create_transfer_log_entry,
	determine_firearm_type,
	parse_serial_nos,
)


def create_firearm_transfer_logs(doc, method):
	if doc.stock_entry_type != "Material Receipt" or not doc.get("custom_rma"):
		return

	rma = frappe.db.get_value("RMA", doc.custom_rma, ["customer", "customer_address"], as_dict=True)

	received_from_address = (
		strip_html(get_address_display(rma.customer_address) or "") if rma.customer_address else None
	)
	customer_name = frappe.db.get_value("Customer", rma.customer, "customer_name") if rma.customer else None
	if customer_name and received_from_address:
		received_from_address = f"{customer_name}\n{received_from_address}"
	elif customer_name:
		received_from_address = customer_name

	for item in doc.items:
		if not frappe.db.get_value("Item", item.item_code, "custom_ffl_required"):
			continue

		serials = parse_serial_nos(item.serial_no)
		if not serials:
			frappe.throw(
				_(
					"Row #{0}: {1} requires a Firearm Transfer Log entry but has no serial number recorded. "
					"Firearms cannot be received without a serial number on file."
				).format(item.idx, item.item_code)
			)

		item_name = frappe.db.get_value("Item", item.item_code, "item_name") or item.item_code

		for serial_no in serials:
			if already_logged("Received", serial_no, rma=doc.custom_rma):
				# Already recorded manually (or on a prior run) in the Firearm Transfer Log
				# for this RMA; don't force type detection or duplicate the entry.
				continue

			firearm_type = determine_firearm_type(item_name)
			create_transfer_log_entry(
				direction="Received",
				transfer_date=doc.posting_date,
				firearm_type=firearm_type,
				serial_no=serial_no,
				source_doctype="Stock Entry",
				source_docname=doc.name,
				rma=doc.custom_rma,
				received_from_address=received_from_address,
			)
