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
	# Only the closing shipment (repaired/replacement unit back to the customer) matters here.
	# Return-label shipments (customer -> us, for RMA pickup) are handled by the Stock Entry hook instead.
	if not doc.get("custom_rma") or doc.get("custom_is_return_label"):
		return

	disposition_type = frappe.db.get_value("RMA", doc.custom_rma, "disposition_type")

	if disposition_type == "Return & Replace":
		# The original unit stays behind in the Repair Bay (scrap/return to vendor/refurbish
		# decided later) — it's NOT what ships. The replacement unit going out to the customer
		# is whatever was issued on the linked Repair Report(s) as a serialized Part row.
		report_names = frappe.get_all("Repair Report", filters={"rma": doc.custom_rma}, pluck="name")
		ffl_items = []
		for row in frappe.get_all(
			"Repair Report Item",
			filters={"parent": ["in", report_names]},
			fields=["item_code", "item_name", "serial_no", "has_serial_no", "quantity_issued", "idx", "parent"],
		) if report_names else []:
			if not row.has_serial_no or not (row.quantity_issued and row.quantity_issued > 0):
				continue
			if frappe.db.get_value("Item", row.item_code, "custom_ffl_required"):
				ffl_items.append(row)
	else:
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
			source_label = f"Repair Report {item.parent}" if item.get("parent") else f"RMA {doc.custom_rma}"
			frappe.throw(
				_(
					"{0}, row #{1}: {2} requires a Firearm Transfer Log entry but has no serial number "
					"recorded. A firearm cannot ship back to the customer without a serial number on file."
				).format(source_label, item.idx, item.item_code)
			)

		firearm_type = None

		for serial_no in serials:
			if already_logged("Sent", serial_no, rma=doc.custom_rma):
				# Already recorded manually (or on a prior run) in the Firearm Transfer Log
				# for this RMA; don't force type detection or duplicate the entry.
				continue

			if firearm_type is None:
				item_name = item.item_name or frappe.get_cached_value("Item", item.item_code, "item_name")
				firearm_type = determine_firearm_type(item_name or item.item_code)

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
