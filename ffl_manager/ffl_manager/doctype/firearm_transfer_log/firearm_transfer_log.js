// Copyright (c) 2026, Chiron Interactive and contributors
// For license information, please see license.txt

frappe.ui.form.on("Firearm Transfer Log", {
	refresh(frm) {
		frm.add_custom_button(__("Copy to Clipboard"), () => copy_filemaker_text(frm));
	},

	sales_order(frm) {
		if (!frm.doc.sales_order) return;
		frappe.call({
			method: "ffl_manager.ffl_manager.doctype.firearm_transfer_log.firearm_transfer_log.fetch_from_sales_order",
			args: { sales_order: frm.doc.sales_order },
			callback(r) {
				if (r.message) frm.set_value(r.message);
			},
		});
	},

	rma(frm) {
		if (!frm.doc.rma) return;
		frappe.call({
			method: "ffl_manager.ffl_manager.doctype.firearm_transfer_log.firearm_transfer_log.fetch_from_rma",
			args: { rma: frm.doc.rma },
			callback(r) {
				if (r.message) frm.set_value(r.message);
			},
		});
	},
});

async function copy_filemaker_text(frm) {
	if (!frm.doc.direction) {
		frappe.msgprint(__("Set Direction (Received/Sent) before copying to clipboard."));
		return;
	}

	const caliber_mapping = await frappe.xcall(
		"ffl_manager.ffl_manager.doctype.firearm_transfer_log.firearm_transfer_log.get_caliber_mapping"
	);

	const text = build_filemaker_clipboard_text(frm.doc, caliber_mapping);
	await navigator.clipboard.writeText(text);
	frappe.show_alert({ message: __("Copied to clipboard"), indicator: "green" });
}

function build_filemaker_clipboard_text(doc, caliber_mapping) {
	const lines = [];
	const set = (key, value) => lines.push(`${key}: ${value || ""}`);

	set("DIRECTION", doc.direction);
	set("DATE", format_date_mmddyyyy(doc.transfer_date));
	set("SERIAL", doc.serial_number);
	set("MAKE", doc.make);
	set("MODEL", doc.model);
	set("TYPE", (doc.firearm_type || "").toUpperCase());
	set("CALIBER", resolve_filemaker_caliber(doc.caliber, caliber_mapping));
	set("NOTES", doc.notes);

	const name = doc.ffl_company_name || doc.recipient_name || "";
	const ffl = doc.ffl_license_number || "";
	set("NAME", name);
	set("FFL", ffl);

	// "Sent to" fields are only populated (by the depends_on rule on the doctype)
	// when direction = Sent, so this naturally comes back blank on Received.
	const address = parse_address_block(doc.sent_to_address);
	set("STREET", address.street);
	set("CITY", address.city);
	set("STATE", address.state);
	set("ZIP", address.zip);

	set("SENT_PARAGRAPH", build_sent_paragraph(name, address, ffl));
	set("RECEIVED_PARAGRAPH", to_escaped_block(doc.received_from_address));

	return lines.join("\n");
}

function resolve_filemaker_caliber(caliber, caliber_mapping) {
	if (!caliber) return "";
	const mapped = caliber_mapping[caliber.toLowerCase()];
	if (mapped) return mapped;
	frappe.show_alert({
		message: __("No FileMaker caliber mapping found for '{0}' — using raw value.", [caliber]),
		indicator: "orange",
	});
	return caliber;
}

function build_sent_paragraph(name, address, ffl) {
	const rows = [];
	if (name) rows.push(name);
	if (address.street) rows.push(address.street);
	if (address.city) rows.push(`${address.city}, ${address.state}  ${address.zip}`);
	if (ffl) rows.push(ffl);
	return rows.join("\\n");
}

function parse_address_block(text) {
	const result = { street: "", city: "", state: "", zip: "" };
	if (!text) return result;

	// Same city/state/zip pattern the original AHK script used, e.g. "Russell Springs, KY 42642".
	const csz_regex = /^(.+?)[,\s]+([A-Za-z]{2})[,\s]+(\d{5}(?:-\d{4})?)$/;
	const street_lines = [];

	for (const raw of text.split(/\r?\n/)) {
		const line = raw.trim();
		if (!line) continue;
		if (result.city) continue; // ignore anything after the city/state/zip line (e.g. country)

		const m = line.match(csz_regex);
		if (m) {
			result.city = m[1].replace(/,\s*$/, "").trim();
			result.state = m[2].toUpperCase();
			result.zip = m[3];
		} else {
			street_lines.push(line);
		}
	}

	result.street = street_lines.join(" ");
	return result;
}

function to_escaped_block(text) {
	return (text || "")
		.split(/\r?\n/)
		.map((line) => line.trim())
		.filter(Boolean)
		.join("\\n");
}

function format_date_mmddyyyy(date_str) {
	if (!date_str) return "";
	const [y, m, d] = date_str.split("-");
	if (!y || !m || !d) return date_str;
	return `${m}/${d}/${y}`;
}
