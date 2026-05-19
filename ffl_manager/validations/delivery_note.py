import frappe


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
            return
