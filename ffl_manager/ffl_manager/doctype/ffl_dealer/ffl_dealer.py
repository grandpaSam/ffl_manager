# Copyright (c) 2026, Chiron Interactive and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document
from frappe.contacts.address_and_contact import load_address_and_contact

#import pytesseract
import re
#from pdf2image import convert_from_path
#from PIL import Image

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

# @frappe.whitelist()
# def extract_ffl_data(file_url):
#
#     if file_url.startswith('/private'):
#         file_path = frappe.get_site_path() + file_url
#     else:
#         file_path = frappe.get_site_path('public') + file_url
#
#     ext = file_url.split('.')[-1].lower()
#
#     if ext == 'pdf':
#         images = convert_from_path(file_path)
#         image = images[0]
#     else:
#         image = Image.open(file_path)
#
#     text = '' #pytesseract.image_to_string(image)
#     result = {}
#
#     # License number - exact FFL format
#     match = re.search(r'(\d-\d{2}-\d{3}-\d{2}-\d[A-Z]-\d{5})', text)
#     result['license_number'] = match.group(1) if match else ''
#
#     # Expiration date
#     match = re.search(r'Expiration[:\s]*([A-Za-z]+ \d+,\s*\d{4})', text)
#     result['expiration_date'] = match.group(1).strip() if match else ''
#
#     # Dealer name
#     match = re.search(r'License Name[}|:]\s*(.+)', text)
#     result['dealer_name'] = match.group(1).strip() if match else ''
#
#     # Address line 1
#     match = re.search(r'Premises Address.*?\n(.+)', text)
#     result['address_line1'] = match.group(1).strip() if match else ''
#
#     # Parse city, state, postal code from address line 2
#     match = re.search(r'Premises Address.*?\n.+\n(.+)', text)
#     if match:
#         address_line2 = match.group(1).strip()
#         parts = re.search(r'^(.+),\s*([A-Z]{2})\s+([\d\-]+)', address_line2)
#         if parts:
#             result['city'] = parts.group(1).strip()
#             result['state'] = parts.group(2).strip()
#             result['postal_code'] = parts.group(3).split('-')[0]
#         else:
#             result['city'] = ''
#             result['state'] = ''
#             result['postal_code'] = ''
#     else:
#         result['city'] = ''
#         result['state'] = ''
#         result['postal_code'] = ''
#     return result



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


class FFLDealer(Document):
    def onload(self):
        load_address_and_contact(self)
