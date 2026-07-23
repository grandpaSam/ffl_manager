import frappe
from frappe import _

from ffl_manager.ffl_manager.doctype.ffl_dealer.ffl_dealer import get_dealer_address_display
from ffl_manager.ffl_manager.doctype.firearm_transfer_log.firearm_transfer_log import fetch_from_sales_order
from ffl_manager.ffl_manager.firearm_transfer import (
	create_transfer_log_entry,
	determine_firearm_type,
	parse_serial_nos,
)


def validate_ffl_required(doc, method):
    if doc.get("custom_skip_ffl_check"):
        return
    for item in doc.items:
        requires_ffl = frappe.db.get_value("Item", item.item_code, "custom_ffl_required")
        if requires_ffl:
            if not item.against_sales_order:
                frappe.throw(
                    f"Item {item.item_code} requires an FFL but this Delivery Note is not linked to a Sales Order."
                )

            ffl_status = frappe.db.get_value("Sales Order", item.against_sales_order, "custom_ffl_status")
            ffl_dealer = frappe.db.get_value("Sales Order", item.against_sales_order, "custom_ffl_dealer")
            if not ffl_dealer or ffl_status != "Received":
                frappe.throw(
                    f"Item {item.item_code} requires an FFL. "
                    f"Please attach an FFL Dealer and mark the status as Received on "
                    f"<a href='/app/sales-order/{item.against_sales_order}'>{item.against_sales_order}</a> before submitting."
                )

            if not get_dealer_address_display(ffl_dealer):
                frappe.throw(
                    f"Item {item.item_code} requires an FFL, but dealer "
                    f"<a href='/app/ffl-dealer/{ffl_dealer}'>{ffl_dealer}</a> has no address on file. "
                    f"A firearm cannot ship without a destination address for the FFL dealer."
                )


def create_firearm_transfer_logs(doc, method):
    if doc.get("custom_skip_ffl_check"):
        return

    dealer_info_cache = {}

    for item in doc.items:
        if not frappe.db.get_value("Item", item.item_code, "custom_ffl_required"):
            continue

        serials = parse_serial_nos(item.serial_no)
        if not serials:
            frappe.throw(
                _(
                    "Row #{0}: {1} requires a Firearm Transfer Log entry but has no serial number recorded. "
                    "Firearms cannot ship without a serial number on file."
                ).format(item.idx, item.item_code)
            )

        if not item.against_sales_order:
            frappe.throw(
                _("Row #{0}: {1} requires an FFL Transfer Log entry but is not linked to a Sales Order.").format(
                    item.idx, item.item_code
                )
            )

        if item.against_sales_order not in dealer_info_cache:
            dealer_info_cache[item.against_sales_order] = fetch_from_sales_order(item.against_sales_order)
        dealer_info = dealer_info_cache[item.against_sales_order]

        item_name = frappe.db.get_value("Item", item.item_code, "item_name") or item.item_code
        firearm_type = determine_firearm_type(item_name)

        for serial_no in serials:
            create_transfer_log_entry(
                direction="Sent",
                transfer_date=doc.posting_date,
                firearm_type=firearm_type,
                serial_no=serial_no,
                source_doctype="Delivery Note",
                source_docname=doc.name,
                sales_order=item.against_sales_order,
                sent_to_address=dealer_info.get("sent_to_address"),
                ffl_license_number=dealer_info.get("ffl_license_number"),
                ffl_company_name=dealer_info.get("ffl_company_name"),
            )
