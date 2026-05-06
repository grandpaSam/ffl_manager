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
		//
		// frm.add_custom_button("Extract FFL Data", function () {
		// 	if (!frm.doc.ffl_copy) {
		// 		frappe.msgprint("Please attach an FFL copy first.");
		// 		return;
		// 	}
		//
		// 	frappe.call({
		// 		method: "ffl_manager.ffl_manager.doctype.ffl_dealer.ffl_dealer.extract_ffl_data",
		// 		args: { file_url: frm.doc.ffl_copy },
		// 		callback: function (r) {
		// 			if (!r.message) return;
		//
		// 			const data = r.message;
		//
		// 			// Populate form fields directly
		// 			frm.set_value("dealer_name", data.dealer_name);
		// 			frm.set_value("license_number", data.license_number);
		//
		// 			// Convert expiration date string to a date value
		// 			if (data.expiration_date) {
		// 				const d = new Date(data.expiration_date);
		// 				frm.set_value("expiration_date", frappe.datetime.obj_to_str(d));
		// 			}
		//
		// 			// Show address review section and fields
		// 			frm.set_df_property("address_review_section", "hidden", 0);
		// 			frm.set_df_property("ocr_address_line1", "hidden", 0);
		// 			frm.set_df_property("ocr_city", "hidden", 0);
		// 			frm.set_df_property("ocr_state", "hidden", 0);
		// 			frm.set_df_property("ocr_postal_code", "hidden", 0);
		//
		// 			// Populate address review fields
		// 			frm.set_value("ocr_address_line1", data.address_line1);
		// 			frm.set_value("ocr_city", data.city);
		// 			frm.set_value("ocr_state", data.state);
		// 			frm.set_value("ocr_postal_code", data.postal_code);
		//
		// 			// Add Create Address button
		// 			frm.add_custom_button("Create Address", function () {
		// 				frappe.call({
		// 					method: "ffl_manager.ffl_manager.doctype.ffl_dealer.ffl_dealer.create_ffl_address",
		// 					args: {
		// 						dealer_name: frm.doc.name,
		// 						address_line1: frm.doc.ocr_address_line1,
		// 						city: frm.doc.ocr_city,
		// 						state: frm.doc.ocr_state,
		// 						postal_code: frm.doc.ocr_postal_code,
		// 					},
		// 					callback: function (r) {
		// 						if (r.message) {
		// 							frappe.msgprint("Address created successfully.");
		//
		// 							// Hide address review section and fields
		// 							frm.set_df_property("address_review_section", "hidden", 1);
		// 							frm.set_df_property("ocr_address_line1", "hidden", 1);
		// 							frm.set_df_property("ocr_city", "hidden", 1);
		// 							frm.set_df_property("ocr_state", "hidden", 1);
		// 							frm.set_df_property("ocr_postal_code", "hidden", 1);
		//
		// 							frm.reload_doc();
		// 						}
		// 					},
		// 				});
		// 			});
		// 		},
		// 	});
		// });
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
