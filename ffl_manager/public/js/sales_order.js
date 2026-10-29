// "Scan FFL Copy" on the FFL tab: run the FFL copy import (ffl_import.js) and
// point this order at the resulting dealer.
frappe.ui.form.on("Sales Order", {
	custom_scan_ffl_copy(frm) {
		frappe.require("/assets/ffl_manager/js/ffl_import.js", () =>
			ffl_manager.import_ffl_copy({ on_saved: (dealer, verified) => set_ffl_dealer(frm, dealer, verified) })
		);
	},
});

function set_ffl_dealer(frm, dealer, verified) {
	// Renewal pending past expiration still counts: ATF's Letter of
	// Authorization lets the licensee keep doing business until it's decided
	const today = frappe.datetime.get_today();
	const valid_until = [verified.expiration_date, verified.loa_expiration_date].filter(Boolean).sort().pop();
	const valid = valid_until >= today;

	frm.set_value("custom_ffl_dealer", dealer);
	if (valid) {
		frm.set_value("custom_ffl_status", "Received");
	} else {
		frappe.msgprint({
			title: __("FFL Expired"),
			indicator: "red",
			message: __("ATF shows {0}'s license expired on {1}. FFL Status was left as {2}.", [
				frappe.utils.escape_html(dealer),
				frappe.datetime.str_to_user(verified.expiration_date),
				frm.doc.custom_ffl_status || __("Pending"),
			]),
		});
	}

	// Submitted orders save these fields via "Update"; drafts save with the order
	if (frm.doc.docstatus === 1) frm.save("Update");
}
