# Copyright (c) 2026, Chiron Interactive and contributors
# For license information, please see license.txt
import frappe
from frappe.contacts.address_and_contact import load_address_and_contact
from frappe.contacts.doctype.address.address import get_address_display
from frappe.model.document import Document
from frappe.utils import strip_html

def archive_ffl_copy(doc, method):
    if doc.attached_to_doctype != "FFL Dealer":
        return

    dealer = frappe.get_doc("FFL Dealer", doc.attached_to_name)

    if doc.file_url == dealer.ffl_copy:
        dealer.append("previous_copies", {
            "ffl_copy": dealer.ffl_copy,
            "expiration_date": dealer.expiration_date,
            "archived_on": frappe.utils.today()
        })
        dealer.ffl_copy = None
        dealer.save()

@frappe.whitelist()
def create_ffl_address(dealer_name, address_line1, city, state, postal_code):
    address = frappe.get_doc({
        'doctype': 'Address',
        'address_title': dealer_name,
        'address_line1': address_line1,
        'city': city,
        'state': state,
        'pincode': postal_code,
        'country': 'United States',
        'links': [{
            'link_doctype': 'FFL Dealer',
            'link_name': dealer_name
        }]
    })
    address.insert()
    return address.name


def get_dealer_address_display(dealer):
    """The dealer's premises address, i.e. where a firearm requiring an FFL must ship."""
    address_name = frappe.db.get_value(
        "Address",
        filters=[
            ["Dynamic Link", "link_doctype", "=", "FFL Dealer"],
            ["Dynamic Link", "link_name", "=", dealer],
            ["Dynamic Link", "parenttype", "=", "Address"],
        ],
        fieldname="name",
        order_by="is_primary_address desc, creation asc",
    )
    if address_name:
        return strip_html(get_address_display(address_name) or "")

    ocr = frappe.db.get_value(
        "FFL Dealer",
        dealer,
        ["ocr_address_line1", "ocr_city", "ocr_state", "ocr_postal_code"],
        as_dict=True,
    )
    if ocr and ocr.ocr_address_line1:
        city_state_zip = " ".join(filter(None, [ocr.ocr_city, ocr.ocr_state, ocr.ocr_postal_code]))
        return "\n".join(filter(None, [ocr.ocr_address_line1, city_state_zip]))

    return None


class FFLDealer(Document):
    def onload(self):
        load_address_and_contact(self)
