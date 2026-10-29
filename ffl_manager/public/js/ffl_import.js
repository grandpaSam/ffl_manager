// Create or update an FFL Dealer from an uploaded FFL copy:
// upload -> OCR -> confirm the number -> ATF eZ Check -> review -> apply.
// Server side: ffl_manager/ffl_lookup/importer.py
frappe.provide("ffl_manager");

(() => {
	const METHOD = "ffl_manager.ffl_lookup.importer.";
	const SEGMENTS = [
		{ length: 1, pattern: /^\d$/, label: __("Region") },
		{ length: 2, pattern: /^\d{2}$/, label: __("District") },
		{ length: 3, pattern: /^\d{3}$/, label: __("County") },
		{ length: 2, pattern: /^\d{2}$/, label: __("Type") },
		{ length: 2, pattern: /^\d[A-HJ-M]$/, label: __("Expiration") },
		{ length: 5, pattern: /^\d{5}$/, label: __("Sequence") },
	];
	const esc = (v) => frappe.utils.escape_html(v == null ? "" : String(v));

	// opts.dealer: update this dealer (form button); otherwise create or match by license
	ffl_manager.import_ffl_copy = function (opts = {}) {
		new frappe.ui.FileUploader({
			dialog_title: __("Upload FFL Copy"),
			allow_multiple: false,
			allow_toggle_private: false,
			allow_web_link: false,
			restrictions: {
				allowed_file_types: [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"],
			},
			on_success: (file) => read_copy(file.file_url, opts),
		});
	};

	function read_copy(file_url, opts) {
		frappe.call({
			method: METHOD + "read_ffl_copy",
			args: { file_url },
			freeze: true,
			freeze_message: __("Reading FFL copy..."),
			callback: (r) => r.message && confirm_number(file_url, r.message, opts),
		});
	}

	function preview_html(file_url) {
		const url = encodeURI(file_url);
		return file_url.toLowerCase().endsWith(".pdf")
			? `<embed src="${url}" type="application/pdf" width="100%" height="520px" />`
			: `<img src="${url}" style="max-width:100%; max-height:520px;" />`;
	}

	function segment_inputs(lic) {
		const segments = lic ? lic.segments : SEGMENTS.map(() => "");
		const confidence = lic ? lic.confidence : SEGMENTS.map(() => "unsure");
		const inputs = SEGMENTS.map((seg, i) => {
			const cls = { ok: "", fixed: "ffl-seg-fixed", unsure: "ffl-seg-unsure" }[confidence[i]];
			return `<div class="ffl-seg">
					<input class="form-control ${cls}" data-seg="${i}" maxlength="${seg.length}"
						style="width:${seg.length * 1.1 + 1.6}em" value="${esc(segments[i])}">
					<div class="small text-muted">${seg.label}</div>
				</div>`;
		});
		return `<style>
				.ffl-segs { display:flex; flex-wrap:wrap; gap:4px; align-items:flex-start; }
				.ffl-seg { text-align:center; }
				.ffl-seg input { font-family:var(--font-family-monospace, monospace); font-size:1.15em;
					text-align:center; text-transform:uppercase; padding:4px; }
				.ffl-seg-fixed { border-color:var(--yellow-500, #e5a00d) !important; }
				.ffl-seg-unsure { border-color:var(--red-500, #e03636) !important; }
				.ffl-dash { padding-top:6px; font-size:1.2em; }
			</style>
			<div class="ffl-segs">${inputs.join('<span class="ffl-dash">-</span>')}</div>`;
	}

	function confirm_number(file_url, data, opts) {
		const lic = data.license;
		let found;
		if (!lic) {
			found = `<div class="alert alert-warning">${__(
				"No license number found on this copy. Type it in from the image."
			)}</div>`;
		} else if (lic.confidence.includes("unsure")) {
			found = `<div class="alert alert-warning">${__(
				"Read as {0}. Check the boxes outlined in red.",
				[`<code>${esc(lic.raw)}</code>`]
			)}</div>`;
		} else {
			found = `<p class="text-muted">${__("Read as {0}.", [`<code>${esc(lic.raw)}</code>`])}</p>`;
		}
		const alternatives = lic && lic.alternatives.length
			? `<p class="small">${__("Other numbers found:")} ${lic.alternatives
					.map((a) => `<a href="#" class="ffl-alt" data-number="${esc(a)}">${esc(a)}</a>`)
					.join(", ")}</p>`
			: "";

		const d = new frappe.ui.Dialog({
			title: __("Confirm FFL Number"),
			size: "extra-large",
			fields: [
				{ fieldtype: "HTML", fieldname: "preview", options: preview_html(file_url) },
				{ fieldtype: "Column Break" },
				{ fieldtype: "HTML", fieldname: "found", options: found },
				{ fieldtype: "HTML", fieldname: "segments", options: segment_inputs(lic) + alternatives },
				{
					fieldtype: "HTML",
					options: `<p class="small text-muted" style="margin-top:8px">${__(
						"Yellow: corrected automatically. Red: couldn't read it. The expiration segment is corrected from ATF's records in the next step."
					)}</p>`,
				},
				{
					fieldtype: "Data",
					fieldname: "signee_name",
					label: __("Signee Name"),
					default: data.signee_name || "",
					description: __("The printed name of the person who signed the copy. Leave blank if unreadable."),
				},
				{ fieldtype: "Section Break", label: __("Text Read From Copy"), collapsible: 1 },
				{
					fieldtype: "HTML",
					options: `<pre style="max-height:300px; overflow:auto; white-space:pre-wrap">${esc(data.text)}</pre>`,
				},
			],
			primary_action_label: __("Look Up on ATF"),
			primary_action(values) {
				const $inputs = d.$wrapper.find(".ffl-seg input");
				const segments = $inputs.map((_, el) => el.value.trim().toUpperCase()).get();
				const bad = SEGMENTS.filter((seg, i) => i !== 4 && !seg.pattern.test(segments[i]));
				if (bad.length) {
					frappe.msgprint(__("Check the {0} segment(s).", [bad.map((s) => s.label).join(", ")]));
					return;
				}
				d.hide();
				verify(file_url, segments.join("-"), values.signee_name, data, opts);
			},
		});
		if (opts.signee_name && !data.signee_name) d.set_value("signee_name", opts.signee_name);

		d.$wrapper.on("input", ".ffl-seg input", function () {
			$(this).removeClass("ffl-seg-fixed ffl-seg-unsure");
		});
		d.$wrapper.on("click", ".ffl-alt", function (e) {
			e.preventDefault();
			const parts = $(this).data("number").split("-");
			d.$wrapper.find(".ffl-seg input").each((i, el) => {
				el.value = parts[i] || "";
				$(el).removeClass("ffl-seg-fixed ffl-seg-unsure");
			});
		});
		d.show();
	}

	function verify(file_url, license_number, signee_name, data, opts) {
		frappe.call({
			method: METHOD + "verify_ffl",
			args: {
				license_number,
				dealer: opts.dealer,
				ocr_expiration_date: data.expiration_date,
				ocr_license_type: data.license_type,
			},
			freeze: true,
			freeze_message: __("Checking ATF FFL eZ Check..."),
			callback: (r) => r.message && review(file_url, r.message, signee_name, opts),
		});
	}

	function format_address(a) {
		if (!a) return "";
		return [a.address_line1, a.address_line2, `${a.city || ""}, ${a.state || ""} ${a.pincode || ""}`]
			.filter((l) => l && l.trim())
			.map(esc)
			.join("<br>");
	}

	function review(file_url, res, signee_name, opts) {
		const cur = res.current;
		const date = (v) => (v ? frappe.datetime.str_to_user(v) : "");
		const rows = [
			[__("License Number"), res.license_number, cur && cur.license_number],
			[__("Expiration Date"), date(res.expiration_date), cur && date(cur.expiration_date)],
			[__("Trade Name"), res.trade_name, cur && cur.trade_name],
			[__("License Name"), res.license_name, cur && cur.license_name],
			[__("License Type"), res.license_type, cur && cur.license_type],
			[__("Signee Name"), signee_name, cur && cur.signee_name],
		];
		const changed = (a, b) => cur && (a || "") !== (b || "");
		const body = rows
			.map(([label, value, current]) => {
				const mark = changed(value, current) ? ' class="ffl-changed"' : "";
				return `<tr><th>${label}</th><td${mark}>${esc(value)}</td>${
					cur ? `<td class="text-muted">${esc(current)}</td>` : ""
				}</tr>`;
			})
			.join("");
		const address_mark = cur && cur.address_changes ? ' class="ffl-changed"' : "";
		const address_row = `<tr><th>${__("Premise Address")}</th><td${address_mark}>${format_address(
			res.premise_address
		)}</td>${
			cur ? `<td class="text-muted">${format_address(cur.address) || __("None")}</td>` : ""
		}</tr>`;

		const warnings = res.warnings
			.map((w) => `<div class="alert alert-warning" style="margin-bottom:6px">${esc(w)}</div>`)
			.join("");
		const heading = res.dealer
			? __("Updating {0}. Changes are highlighted.", [`<b>${esc(res.dealer)}</b>`])
			: __("No dealer on file with this license. A new FFL Dealer will be created.");
		const address_note =
			cur && cur.address_changes && cur.address
				? `<p class="small text-muted">${__(
						"The premise address changed: a new primary shipping address will be added and the old one kept."
				  )}</p>`
				: "";

		const html = `<style>
				.ffl-review th { width:28%; } .ffl-changed { background:var(--yellow-highlight-color, #fff5cc); }
			</style>
			${warnings}<p>${heading}</p>
			<table class="table table-bordered ffl-review">
				<thead><tr><th></th><th>${__("From ATF")}</th>${cur ? `<th>${__("Current")}</th>` : ""}</tr></thead>
				<tbody>${body}${address_row}</tbody>
			</table>${address_note}`;

		const fields = [{ fieldtype: "HTML", options: html }];
		if (!res.dealer) {
			fields.push({
				fieldtype: "Data",
				fieldname: "dealer_name",
				label: __("Dealer Name"),
				reqd: 1,
				default: res.suggested_dealer_name,
			});
		}

		const d = new frappe.ui.Dialog({
			title: __("Review FFL Dealer"),
			size: "large",
			fields,
			primary_action_label: res.dealer ? __("Update {0}", [res.dealer]) : __("Create Dealer"),
			primary_action(values) {
				frappe.call({
					method: METHOD + "apply_ffl_copy",
					args: {
						file_url,
						license_number: res.license_number,
						dealer: res.dealer,
						dealer_name: values.dealer_name,
						signee_name,
					},
					freeze: true,
					freeze_message: __("Saving..."),
					callback: (r) => {
						if (!r.message) return;
						d.hide();
						frappe.show_alert({ message: __("FFL Dealer {0} saved", [r.message]), indicator: "green" });
						if (opts.frm && opts.frm.doc.name === r.message) {
							opts.frm.reload_doc();
						} else {
							frappe.set_route("Form", "FFL Dealer", r.message);
						}
					},
				});
			},
		});
		d.show();
	}
})();
