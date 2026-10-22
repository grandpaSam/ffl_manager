// Red "RESTRICTED BUILD" banner on a Work Order whose State Compliance
// Rules substitution fired - see ffl_manager.validations.work_order.validate,
// which sets custom_restricted_build / custom_compliance_state /
// custom_compliance_changes.

frappe.ui.form.on("Work Order", {
	refresh(frm) {
		if (!frm.doc.custom_restricted_build) return;

		frm.dashboard.set_headline_alert(
			`<div class="row">
				<div class="col-xs-12">
					<strong>${__("RESTRICTED BUILD")} (${frappe.utils.escape_html(frm.doc.custom_compliance_state || "")}):</strong>
					${frappe.utils.escape_html(frm.doc.custom_compliance_changes || "")}
				</div>
			</div>`,
			"red"
		);
	},
});
