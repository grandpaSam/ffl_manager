// "Create Compliance Rework" button: for a restricted-state Delivery Note
// shipping a finished good that was built to standard spec (no matching
// restricted-build Work Order found for its Sales Order - see
// ffl_manager.validations.compliance_delivery_note.validate_compliance),
// lets the builder create the Repack Stock Entry that converts it before
// submitting. Shown on draft Delivery Notes only; the actual gating logic
// lives server-side (before_submit), this button is just a convenience to
// fix the problem it reports.

frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		if (!(frm.doc.items || []).length) return;

		frm.add_custom_button(__("Create Compliance Rework"), () => show_compliance_rework_dialog(frm));
	},
});

function show_compliance_rework_dialog(frm) {
	const item_options = frm.doc.items
		.filter((row) => row.item_code)
		.map((row) => ({
			label: `Row #${row.idx}: ${row.item_code}${row.custom_compliance_rework ? " (rework already linked)" : ""}`,
			value: row.name,
		}));

	const dialog = new frappe.ui.Dialog({
		title: __("Create Compliance Rework"),
		fields: [
			{
				fieldtype: "Select",
				fieldname: "item_row",
				label: __("Delivery Note Row"),
				options: item_options,
				reqd: 1,
			},
		],
		primary_action_label: __("Create"),
		primary_action(data) {
			frappe.dom.freeze(__("Creating rework entry..."));
			frappe
				.xcall("ffl_manager.validations.compliance_rework.create_compliance_rework", {
					delivery_note: frm.doc.name,
					item_row_name: data.item_row,
				})
				.then((stock_entry) => {
					frappe.dom.unfreeze();
					dialog.hide();
					frappe.show_alert({ message: __("Rework entry created"), indicator: "green" });
					frm.reload_doc().then(() => {
						frappe.set_route("Form", "Stock Entry", stock_entry);
					});
				})
				.catch(() => frappe.dom.unfreeze());
		},
	});

	dialog.show();
}
