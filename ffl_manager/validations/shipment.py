import frappe
from frappe import _
from frappe.contacts.doctype.address.address import get_address_display
from frappe.utils import strip_html

from ffl_manager.ffl_manager.firearm_transfer import (
	create_transfer_log_entry,
	determine_firearm_type,
	parse_serial_nos,
)


def create_firearm_transfer_logs(doc, method):
	# Only the closing shipment (repaired/replacement unit back to the customer) matters here.
	# Return-label shipments (customer -> us, for RMA pickup) are handled by the Stock Entry hook instead.
	if not doc.get("custom_rma") or doc.get("custom_is_return_label"):
		return

	rma_items = frappe.get_all(
		"RMA Item",
		filters={"parent": doc.custom_rma, "parenttype": "RMA"},
		fields=["item_code", "item_name", "serial_no", "has_serial_no", "idx"],
	)
	ffl_items = [
		item
		for item in rma_items
		if item.has_serial_no and frappe.db.get_value("Item", item.item_code, "custom_ffl_required")
	]
	if not ffl_items:
		return

	customer = frappe.db.get_value("RMA", doc.custom_rma, "customer")
	recipient_name = frappe.db.get_value("Customer", customer, "customer_name") if customer else None
	sent_to_address = (
		strip_html(get_address_display(doc.delivery_address_name) or "") if doc.get("delivery_address_name") else None
	)
	transfer_date = doc.pickup_date or frappe.utils.today()

	for item in ffl_items:
		serials = parse_serial_nos(item.serial_no)
		if not serials:
			frappe.throw(
				_(
					"RMA {0}, row #{1}: {2} requires a Firearm Transfer Log entry but has no serial number "
					"recorded. A firearm cannot ship back to the customer without a serial number on file."
				).format(doc.custom_rma, item.idx, item.item_code)
			)

		firearm_type = determine_firearm_type(item.item_name or item.item_code)

		for serial_no in serials:
			create_transfer_log_entry(
				direction="Sent",
				transfer_date=transfer_date,
				firearm_type=firearm_type,
				serial_no=serial_no,
				source_doctype="Shipment",
				source_docname=doc.name,
				rma=doc.custom_rma,
				sent_to_address=sent_to_address,
				recipient_name=recipient_name,
			)
