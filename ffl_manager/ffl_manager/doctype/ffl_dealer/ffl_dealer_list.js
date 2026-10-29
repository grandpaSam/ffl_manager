frappe.listview_settings["FFL Dealer"] = {
	onload(listview) {
		listview.page.add_inner_button(__("New from FFL Copy"), () =>
			frappe.require("/assets/ffl_manager/js/ffl_import.js", () => ffl_manager.import_ffl_copy())
		);
	},
};
