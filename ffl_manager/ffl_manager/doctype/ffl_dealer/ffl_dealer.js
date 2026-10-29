// Copyright (c) 2026, Chiron Interactive and contributors
// For license information, please see license.txt

// frappe.ui.form.on("FFL Dealer", {
// 	refresh(frm) {

// 	},
// });
//
frappe.ui.form.on("FFL Dealer", {
	onload: function (frm) {
		if (!frm.doc.__islocal) {
			frappe.contacts.render_address_and_contact(frm);
		} else {
			frappe.contacts.clear_address_and_contact(frm);
		}
		render_ffl_preview(frm);
	},

	refresh: function (frm) {
		render_ffl_preview(frm);
		frm.add_custom_button(frm.is_new() ? __("Fill from FFL Copy") : __("Update from FFL Copy"), () =>
			frappe.require("/assets/ffl_manager/js/ffl_import.js", () =>
				ffl_manager.import_ffl_copy({
					dealer: frm.is_new() ? null : frm.doc.name,
					signee_name: frm.doc.signee_name,
					frm,
				})
			)
		);
	},
});

function render_ffl_preview(frm) {
	const file_url = frm.doc.ffl_copy;
	const wrapper = frm.fields_dict.ffl_preview_html.$wrapper;

	if (!file_url) {
		wrapper.html('<p class="text-muted">No FFL copy attached.</p>');
		return;
	}

	const ext = file_url.split(".").pop().toLowerCase();

	if (ext === "pdf") {
		wrapper.html(`
            <embed src="${file_url}" type="application/pdf" width="100%" height="600px" />
        `);
	} else {
		wrapper.html(`
            <img src="${file_url}" style="max-width:100%; height:auto;" />
        `);
	}
}
