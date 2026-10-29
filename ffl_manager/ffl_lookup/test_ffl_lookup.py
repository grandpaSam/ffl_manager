import datetime
import os
import unittest

from ffl_manager.ffl_lookup import ezcheck, ocr

TEST_DATA = os.path.join(os.path.dirname(__file__), "test_data")


def _read(name):
	with open(os.path.join(TEST_DATA, name)) as f:
		return f.read()


class TestParseLicenseNumber(unittest.TestCase):
	def test_real_ocr_output(self):
		# Tesseract's read of a real license (identifying details replaced),
		# which garbled 8K as "a K" and also caught the microprint strip
		parsed = ocr.parse_license_number(_read("ocr_license_copy.txt"))
		self.assertEqual(parsed["segments"][:4], ["9", "12", "345", "01"])
		self.assertEqual(parsed["segments"][5], "67890")
		self.assertEqual(parsed["confidence"][4], "unsure")

	def test_clean_number(self):
		parsed = ocr.parse_license_number("License Number 9-12-345-01-8K-67890")
		self.assertEqual(parsed["license_number"], "9-12-345-01-8K-67890")
		self.assertEqual(parsed["confidence"], ["ok"] * 6)

	def test_repairs_misread_digits(self):
		parsed = ocr.parse_license_number("Number 9-l2-34S-0l-8K-6789O")
		self.assertEqual(parsed["license_number"], "9-12-345-01-8K-67890")
		self.assertEqual(parsed["confidence"], ["ok", "fixed", "fixed", "fixed", "ok", "fixed"])

	def test_spaces_instead_of_dashes(self):
		parsed = ocr.parse_license_number("9 12 345 01 8K 67890")
		self.assertEqual(parsed["license_number"], "9-12-345-01-8K-67890")

	def test_unknown_license_type_is_unsure(self):
		parsed = ocr.parse_license_number("9-12-345-04-8K-67890")
		self.assertEqual(parsed["confidence"][3], "unsure")

	def test_ignores_phone_numbers(self):
		self.assertIsNone(ocr.parse_license_number("Call 1-866-662-2750 or 303.955.4800"))

	def test_labelled_number_wins(self):
		text = "6-11-222-01-8K-33333\nLicense Number 9-12-345-01-8K-67890"
		parsed = ocr.parse_license_number(text)
		self.assertEqual(parsed["license_number"], "9-12-345-01-8K-67890")
		self.assertEqual(parsed["alternatives"], ["6-11-222-01-8K-33333"])


class TestOcrHints(unittest.TestCase):
	def setUp(self):
		self.text = _read("ocr_license_copy.txt")

	def test_expiration_date(self):
		self.assertEqual(ocr.parse_expiration_date(self.text), "2028-10-01")

	def test_license_type(self):
		self.assertEqual(ocr.parse_license_type(self.text), "01")

	def test_signee_name(self):
		self.assertEqual(ocr.parse_signee_name(self.text), "Jane Example")

	def test_expiration_segment(self):
		self.assertEqual(ocr.expiration_segment(datetime.date(2028, 10, 1)), "8K")
		self.assertEqual(ocr.expiration_segment(datetime.date(2030, 9, 1)), "0J")  # no "I"
		self.assertEqual(ocr.expiration_segment(datetime.date(2027, 12, 1)), "7M")


class TestEzCheckParse(unittest.TestCase):
	def test_found(self):
		result = ezcheck.parse_result(_read("ezcheck_found.html"))
		self.assertEqual(result["masked_license_number"], "9-12-XXX-XX-XX-67890")
		self.assertEqual(result["expiration_date"], datetime.date(2028, 10, 1))
		self.assertEqual(result["license_name"], "MESA RIDGE HOLDINGS LLC")
		self.assertEqual(result["trade_name"], "MESA RIDGE ARMORY")
		self.assertEqual(
			result["premise_address"],
			{
				"address_line1": "1200 SAMPLE CANYON ROAD",
				"address_line2": "",
				"city": "FAIRVIEW",
				"state": "CO",
				"pincode": "80999",
			},
		)
		self.assertIsNone(result["loa_expiration_date"])

	def test_not_found(self):
		with self.assertRaises(ezcheck.LicenseNotFound):
			ezcheck.parse_result(_read("ezcheck_not_found.html"))

	def test_unrecognized_page(self):
		with self.assertRaises(ezcheck.EzCheckError):
			ezcheck.parse_result("<html><body>Service unavailable</body></html>")

	def test_two_line_street(self):
		address = ezcheck.parse_address(["123 MAIN ST", "SUITE 4", "SPRINGFIELD", "IL - 62701-1234"])
		self.assertEqual(address["address_line2"], "SUITE 4")
		self.assertEqual(address["pincode"], "62701-1234")
