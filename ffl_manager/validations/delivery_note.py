import frappe
from frappe import _

from ffl_manager.ffl_manager.doctype.ffl_dealer.ffl_dealer import get_dealer_address_display
from ffl_manager.ffl_manager.doctype.firearm_transfer_log.firearm_transfer_log import fetch_from_sales_order
from ffl_manager.ffl_manager.firearm_transfer import (
    already_logged,
    create_transfer_log_entry,
    determine_firearm_type,
    parse_serial_nos,
)


def _get_ffl_rows(doc, item):
    """Return the rows to run FFL checks against for a given Delivery Note item row.

    Product Bundle items are exploded into ``packed_items`` for their stock
    components, and the serial number / custom_ffl_required flag live on those
    component rows rather than on the bundle parent row itself.
    """
    packed_items = [
        row for row in (doc.get("packed_items") or []) if row.parent_detail_docname == item.name
    ]
    return packed_items if packed_items else [item]


def validate_ffl_required(doc, method):
    if doc.get("custom_skip_ffl_check"):
        return
    for item in doc.items:
        for row in _get_ffl_rows(doc, item):
            requires_ffl = frappe.db.get_value("Item", row.item_code, "custom_ffl_required")
            if requires_ffl:
                if not item.against_sales_order:
                    frappe.throw(
                        f"Item {row.item_code} requires an FFL but this Delivery Note is not linked to a Sales Order."
                    )

                ffl_status = frappe.db.get_value("Sales Order", item.against_sales_order, "custom_ffl_status")
                ffl_dealer = frappe.db.get_value("Sales Order", item.against_sales_order, "custom_ffl_dealer")
                if not ffl_dealer or ffl_status != "Received":
                    frappe.throw(
                        f"Item {row.item_code} requires an FFL. "
                        f"Please attach an FFL Dealer and mark the status as Received on "
                        f"<a href='/app/sales-order/{item.against_sales_order}'>{item.against_sales_order}</a> before submitting."
                    )

                if not get_dealer_address_display(ffl_dealer):
                    frappe.throw(
                        f"Item {row.item_code} requires an FFL, but dealer "
                        f"<a href='/app/ffl-dealer/{ffl_dealer}'>{ffl_dealer}</a> has no address on file. "
                        f"A firearm cannot ship without a destination address for the FFL dealer."
                    )


def create_firearm_transfer_logs(doc, method):
    # NB: unlike validate_ffl_required, this does NOT bail on custom_skip_ffl_check.
    # A repair-return DN (RMA-linked, no FFL dealer) still ships without routing
    # through an FFL, but the bound-book disposition entry must still be written.
    dealer_info_cache = {}

    for item in doc.items:
        for row in _get_ffl_rows(doc, item):
            if not frappe.db.get_value("Item", row.item_code, "custom_ffl_required"):
                continue

            serials = parse_serial_nos(row.serial_no)
            if not serials:
                frappe.throw(
                    _(
                        "Row #{0}: {1} requires a Firearm Transfer Log entry but has no serial number recorded. "
                        "Firearms cannot ship without a serial number on file."
                    ).format(item.idx, row.item_code)
                )

            if not item.against_sales_order:
                frappe.throw(
                    _("Row #{0}: {1} requires an FFL Transfer Log entry but is not linked to a Sales Order.").format(
                        item.idx, row.item_code
                    )
                )

            if item.against_sales_order not in dealer_info_cache:
                dealer_info_cache[item.against_sales_order] = fetch_from_sales_order(item.against_sales_order)
            dealer_info = dealer_info_cache[item.against_sales_order]

            # Repair returns come in via an RMA-linked Sales Order; link the disposition
            # entry to both the SO and the RMA (mirrors the RMA-receipt acquisition entry).
            rma = frappe.db.get_value("Sales Order", item.against_sales_order, "custom_rma")

            item_name = frappe.db.get_value("Item", row.item_code, "item_name") or row.item_code

            for serial_no in serials:
                if already_logged("Sent", serial_no, sales_order=item.against_sales_order, rma=rma):
                    # Already recorded manually (or on a prior run) in the Firearm Transfer Log
                    # for this Sales Order / RMA; don't force type detection or duplicate the entry.
                    continue

                firearm_type = determine_firearm_type(item_name)
                create_transfer_log_entry(
                    direction="Sent",
                    transfer_date=doc.posting_date,
                    firearm_type=firearm_type,
                    serial_no=serial_no,
                    source_doctype="Delivery Note",
                    source_docname=doc.name,
                    sales_order=item.against_sales_order,
                    rma=rma,
                    sent_to_address=dealer_info.get("sent_to_address"),
                    ffl_license_number=dealer_info.get("ffl_license_number"),
                    ffl_company_name=dealer_info.get("ffl_company_name"),
                    recipient_name=dealer_info.get("recipient_name"),
                )
