// Copyright (c) 2026, Chiron Interactive and contributors
// For license information, please see license.txt

frappe.ui.form.on("Firearm Transfer Log", {
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
