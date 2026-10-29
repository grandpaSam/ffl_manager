"""Pull the license number (and a few hints) off a scanned/photographed FFL.

An FFL number is six segments: region-district-county-type-expiration-sequence,
e.g. 9-12-345-01-8K-67890. Tesseract mangles it often enough (that very
license came back as "9-12-345-01 a K-67890") that an exact regex is useless,
so parse_license_number() matches loosely, repairs common misreads per segment
and reports how sure it is about each one. The user confirms the result, and
ezcheck can then repair the expiration segment from ATF's expiration date.
"""

import datetime
import re

LICENSE_TYPES = {
	"01": "Dealer in Firearms Other Than Destructive Devices",
	"02": "Pawnbroker in Firearms Other Than Destructive Devices",
	"03": "Collector of Curios and Relics",
	"06": "Manufacturer of Ammunition for Firearms",
	"07": "Manufacturer of Firearms Other Than Destructive Devices",
	"08": "Importer of Firearms Other Than Destructive Devices",
	"09": "Dealer in Destructive Devices",
	"10": "Manufacturer of Destructive Devices",
	"11": "Importer of Destructive Devices",
}

# 5th segment: last digit of the expiration year + month letter (A-M, no I)
MONTH_LETTERS = "ABCDEFGHJKLM"

SEGMENT_LENGTHS = (1, 2, 3, 2, 2, 5)


def expiration_segment(expiration_date):
	"""The 5th license segment for an expiration date, e.g. 2028-10-01 -> "8K"."""
	return f"{expiration_date.year % 10}{MONTH_LETTERS[expiration_date.month - 1]}"

_TO_DIGIT = str.maketrans("OoQDIl|!SsBZzGb", "000011115582266")
_TO_LETTER = str.maketrans("08152", "OBISZ")

_C = r"[0-9A-Za-z|!]"
_SEP = r"(?:\s*[-–—_.~=]\s*|\s+)"
_LICENSE_RE = re.compile(
	rf"(?<![0-9A-Za-z])({_C}){_SEP}({_C}{{2}}){_SEP}({_C}{{3}}){_SEP}({_C}{{2}}){_SEP}"
	rf"({_C})\s*({_C}){_SEP}({_C}{{5}})(?![0-9A-Za-z])"
)

_MONTHS = (
	"january|february|march|april|may|june|july|august|september|october|november|december"
)
_EXPIRATION_RE = re.compile(rf"\b({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.IGNORECASE)
_TYPE_RE = re.compile(r"\b(0[1-9]|1[01])\s*[-–]\s*(DEALER|PAWNBROKER|COLLECTOR|MANUFACTURER|IMPORTER)")
# The license number's own label, so the real number outranks the microprint
# strip along the bottom edge (which also contains a copy of it, badly OCR'd)
_NUMBER_LABEL_RE = re.compile(r"(License\s+)?Number", re.IGNORECASE)


def _digits(raw, length):
	"""(value, confidence) for an all-digit segment."""
	fixed = raw.translate(_TO_DIGIT)
	if not fixed.isdigit() or len(fixed) != length:
		return raw.upper(), "unsure"
	return fixed, "ok" if fixed == raw else "fixed"


def _read_expiration_segment(year_char, month_char):
	year, year_conf = _digits(year_char, 1)
	month = month_char.upper().translate(_TO_LETTER)
	if month in MONTH_LETTERS:
		month_conf = "ok" if month == month_char.upper() else "fixed"
	else:
		month_conf = "unsure"
	if "unsure" in (year_conf, month_conf):
		conf = "unsure"
	elif "fixed" in (year_conf, month_conf):
		conf = "fixed"
	else:
		conf = "ok"
	return year + month, conf


def _segments_from_match(m):
	groups = m.groups()
	segments, confidence = [], []
	for raw, length in zip((groups[0], groups[1], groups[2], groups[3]), SEGMENT_LENGTHS[:4]):
		value, conf = _digits(raw, length)
		segments.append(value)
		confidence.append(conf)

	value, conf = _read_expiration_segment(groups[4], groups[5])
	segments.append(value)
	confidence.append(conf)

	value, conf = _digits(groups[6], 5)
	segments.append(value)
	confidence.append(conf)

	if confidence[3] != "unsure" and segments[3] not in LICENSE_TYPES:
		confidence[3] = "unsure"
	return segments, confidence


def _score(text, m, confidence):
	points = {"ok": 2, "fixed": 1, "unsure": 0}
	score = sum(points[c] for c in confidence)
	line_start = text.rfind("\n", 0, m.start()) + 1
	if _NUMBER_LABEL_RE.search(text[max(0, line_start - 80) : m.start()]):
		score += 3
	return score


def parse_license_number(text):
	"""Best guess at the license number in OCR'd text, or None.

	Returns {"segments": [6 strings], "confidence": [6 x "ok"|"fixed"|"unsure"],
	"license_number", "raw" (the matched text), "alternatives": [other numbers]}.
	"""
	candidates = []
	for m in _LICENSE_RE.finditer(text):
		segments, confidence = _segments_from_match(m)
		candidates.append(
			{
				"segments": segments,
				"confidence": confidence,
				"license_number": "-".join(segments),
				"raw": m.group(0),
				"score": _score(text, m, confidence),
			}
		)
	if not candidates:
		return None

	candidates.sort(key=lambda c: c["score"], reverse=True)
	best = candidates[0]
	best["alternatives"] = list(
		dict.fromkeys(
			c["license_number"] for c in candidates[1:] if c["license_number"] != best["license_number"]
		)
	)
	return best


def is_confident(parsed):
	return bool(parsed) and "unsure" not in parsed["confidence"]


def parse_expiration_date(text):
	"""The first written-out date ("October 1, 2028") as YYYY-MM-DD, or None."""
	m = _EXPIRATION_RE.search(text)
	if not m:
		return None
	month = _MONTHS.split("|").index(m.group(1).lower()) + 1
	return f"{m.group(3)}-{month:02d}-{int(m.group(2)):02d}"


def parse_license_type(text):
	m = _TYPE_RE.search(text.upper())
	return m.group(1) if m else None


def parse_signee_name(text):
	"""The printed name above the "Printed Name" caption, if OCR caught it.

	It shares a line with the signature date ("Noah Miller 08/05/2025"), so
	the date is stripped. Often illegible - the user can type it instead.
	"""
	lines = text.splitlines()
	for i, line in enumerate(lines):
		if re.match(r"\s*Printed\s+Name", line, re.IGNORECASE) and i > 0:
			name = re.sub(r"\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s*$", "", lines[i - 1]).strip()
			if re.fullmatch(r"[A-Za-z][A-Za-z .,'-]{2,60}", name):
				return name
	return None


def extract_text(file_path, max_pages=3):
	"""Yield text for each "page" worth trying, cheapest source first.

	PDFs: the embedded text layer, then each page rendered and OCR'd.
	Images: the image as-is, then rotated 90/180/270 (phone photos).
	Callers stop as soon as they find what they need.
	"""
	import pytesseract
	from PIL import Image, ImageOps

	if file_path.lower().endswith(".pdf"):
		from pdf2image import convert_from_path
		from pypdf import PdfReader

		try:
			layer = "\n".join(page.extract_text() or "" for page in PdfReader(file_path).pages[:max_pages])
		except Exception:
			layer = ""
		if layer.strip():
			yield layer
		for page in range(1, max_pages + 1):
			images = convert_from_path(file_path, dpi=300, first_page=page, last_page=page)
			if not images:
				break
			yield pytesseract.image_to_string(images[0].convert("L"))
		return

	image = ImageOps.exif_transpose(Image.open(file_path)).convert("L")
	for angle in (0, 90, 180, 270):
		yield pytesseract.image_to_string(image.rotate(angle, expand=True) if angle else image)


def extract_ffl_data(file_path):
	"""OCR an FFL copy. Returns the parsed number (or None) plus hints.

	{"license": parse_license_number() result or None, "expiration_date",
	"license_type", "signee_name", "text": all OCR text read}
	"""
	texts, best = [], None
	for text in extract_text(file_path):
		texts.append(text)
		parsed = parse_license_number(text)
		if parsed and (not best or parsed["score"] > best["score"]):
			best = parsed
		if is_confident(best):
			break

	text = "\n\n".join(texts)
	expiration_date = parse_expiration_date(text)
	if best and best["confidence"][4] == "unsure" and expiration_date:
		# The printed expiration date spells out the segment OCR garbled
		best["segments"][4] = expiration_segment(datetime.date.fromisoformat(expiration_date))
		best["confidence"][4] = "fixed"
		best["license_number"] = "-".join(best["segments"])

	return {
		"license": best,
		"expiration_date": expiration_date,
		"license_type": parse_license_type(text),
		"signee_name": parse_signee_name(text),
		"text": text,
	}
