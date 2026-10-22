# Copyright (c) 2026, Chiron Interactive and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document


class StateComplianceRule(Document):
	def validate(self):
		if not self.states:
			frappe.throw(_("At least one State is required."))
		if not self.substitutions:
			frappe.throw(_("At least one Substitution is required."))

	def on_update(self):
		from ffl_manager.compliance.engine import clear_rule_cache

		clear_rule_cache()

	def on_trash(self):
		from ffl_manager.compliance.engine import clear_rule_cache

		clear_rule_cache()
