import unittest
from unittest.mock import patch

import frappe

from ffl_manager.compliance.engine import apply, normalize_state, _rule_applies

# frappe._ (gettext) needs a bound site to run; since these tests exercise
# engine.py with frappe itself mocked out (no site), also stub out the
# translation wrapper engine.py imported directly (`from frappe import _`)
# so the throw-message formatting in _get_item_or_throw doesn't blow up
# before frappe.throw (itself mocked with a raising side_effect) is reached.
_PATCH_GETTEXT = patch("ffl_manager.compliance.engine._", lambda s: s)


class TestNormalizeState(unittest.TestCase):
	def test_already_a_code_uppercase(self):
		self.assertEqual(normalize_state("OR"), "OR")

	def test_code_lowercase(self):
		self.assertEqual(normalize_state("ar"), "AR")

	def test_code_mixed_case(self):
		self.assertEqual(normalize_state("Tn"), "TN")

	def test_full_name(self):
		self.assertEqual(normalize_state("Ohio"), "OH")

	def test_full_name_lowercase(self):
		self.assertEqual(normalize_state("texas"), "TX")

	def test_full_name_with_extra_whitespace(self):
		self.assertEqual(normalize_state("  New   York  "), "NY")

	def test_district_of_columbia_variants(self):
		self.assertEqual(normalize_state("District of Columbia"), "DC")
		self.assertEqual(normalize_state("Washington DC"), "DC")

	def test_blank_returns_none(self):
		self.assertIsNone(normalize_state(""))
		self.assertIsNone(normalize_state(None))
		self.assertIsNone(normalize_state("   "))

	def test_unmappable_returns_none(self):
		self.assertIsNone(normalize_state("Not A Real State"))


class TestRuleApplies(unittest.TestCase):
	def _rule(self, **overrides):
		rule = {
			"name": "RULE-1",
			"rule_name": "Test Rule",
			"enabled": True,
			"states": ["WA", "CA"],
			"applies_to_item_group": None,
			"substitutions": [],
		}
		rule.update(overrides)
		return rule

	def test_matches_state(self):
		self.assertTrue(_rule_applies(self._rule(), "WA"))

	def test_state_not_in_list_fails(self):
		self.assertFalse(_rule_applies(self._rule(), "TX"))

	def test_disabled_rule_ignored(self):
		self.assertFalse(_rule_applies(self._rule(enabled=False), "WA"))

	def test_no_item_group_restriction_matches_any_item_group(self):
		self.assertTrue(_rule_applies(self._rule(), "WA", item_group="Firearms"))

	def test_item_group_restriction_matches(self):
		rule = self._rule(applies_to_item_group="Firearms")
		self.assertTrue(_rule_applies(rule, "WA", item_group="Firearms"))

	def test_item_group_restriction_mismatch_fails(self):
		rule = self._rule(applies_to_item_group="Firearms")
		self.assertFalse(_rule_applies(rule, "WA", item_group="Accessories"))

	def test_item_group_restriction_with_no_item_group_given_fails(self):
		rule = self._rule(applies_to_item_group="Firearms")
		self.assertFalse(_rule_applies(rule, "WA", item_group=None))


class TestApplyReplace(unittest.TestCase):
	def _rows(self):
		return [
			{"item_code": "ASRX-XPKG-9MM-EXT", "item_name": "9mm Extended Mag", "qty": 1, "stock_uom": "Each",
			 "source_warehouse": "Stores - TNW"},
			{"item_code": "GRIP-STD", "item_name": "Standard Grip", "qty": 1, "stock_uom": "Each",
			 "source_warehouse": "Stores - TNW"},
		]

	@patch("ffl_manager.compliance.engine.frappe")
	def test_replace_swaps_item_and_refreshes_fields(self, mock_frappe):
		mock_frappe.db.get_value.return_value = frappe._dict({
			"item_name": "9mm Standard Mag",
			"description": "Standard capacity 9mm magazine",
			"stock_uom": "Each",
		})

		rows = self._rows()
		rules = [
			{
				"rule_name": "WA Mag Swap",
				"substitutions": [
					{"action": "Replace", "from_item": "ASRX-XPKG-9MM-EXT", "to_item": "ASRX-XPKG-9MM-STN"}
				],
			}
		]

		changes = apply(rows, rules)

		self.assertEqual(rows[0]["item_code"], "ASRX-XPKG-9MM-STN")
		self.assertEqual(rows[0]["item_name"], "9mm Standard Mag")
		self.assertEqual(rows[0]["description"], "Standard capacity 9mm magazine")
		self.assertEqual(rows[1]["item_code"], "GRIP-STD")  # untouched
		self.assertEqual(len(changes), 1)
		self.assertEqual(changes[0]["action"], "Replace")
		self.assertEqual(changes[0]["to_item"], "ASRX-XPKG-9MM-STN")

	@patch("ffl_manager.compliance.engine.frappe")
	def test_replace_with_no_matching_row_is_a_no_op(self, mock_frappe):
		rows = self._rows()
		rules = [
			{
				"rule_name": "No Match",
				"substitutions": [
					{"action": "Replace", "from_item": "DOES-NOT-EXIST", "to_item": "ALSO-IRRELEVANT"}
				],
			}
		]

		changes = apply(rows, rules)

		self.assertEqual(changes, [])
		mock_frappe.db.get_value.assert_not_called()

	@_PATCH_GETTEXT
	@patch("ffl_manager.compliance.engine.frappe")
	def test_replace_missing_to_item_fails_clearly(self, mock_frappe, _mock_gettext=None):
		mock_frappe.db.get_value.return_value = None
		mock_frappe.throw.side_effect = Exception("boom")

		rows = self._rows()
		rules = [
			{
				"rule_name": "Bad Rule",
				"substitutions": [
					{"action": "Replace", "from_item": "ASRX-XPKG-9MM-EXT", "to_item": "ASRX-XPKG-XX22-STN"}
				],
			}
		]

		with self.assertRaises(Exception):
			apply(rows, rules)
		mock_frappe.throw.assert_called_once()


class TestApplyRemove(unittest.TestCase):
	@patch("ffl_manager.compliance.engine.frappe")
	def test_remove_drops_matching_rows(self, mock_frappe):
		rows = [
			{"item_code": "GRIP-DELUXE", "qty": 1},
			{"item_code": "ASRX-XPKG-9MM-EXT", "qty": 1},
		]
		rules = [
			{
				"rule_name": "No Deluxe Grip",
				"substitutions": [{"action": "Remove", "from_item": "GRIP-DELUXE"}],
			}
		]

		changes = apply(rows, rules)

		self.assertEqual([r["item_code"] for r in rows], ["ASRX-XPKG-9MM-EXT"])
		self.assertEqual(len(changes), 1)
		self.assertEqual(changes[0]["action"], "Remove")
		mock_frappe.db.get_value.assert_not_called()

	@patch("ffl_manager.compliance.engine.frappe")
	def test_remove_with_no_matching_row_is_a_no_op(self, mock_frappe):
		rows = [{"item_code": "GRIP-DELUXE", "qty": 1}]
		rules = [
			{
				"rule_name": "No Match",
				"substitutions": [{"action": "Remove", "from_item": "NOT-PRESENT"}],
			}
		]

		changes = apply(rows, rules)

		self.assertEqual(len(rows), 1)
		self.assertEqual(changes, [])


class TestApplyAdd(unittest.TestCase):
	@patch("ffl_manager.compliance.engine.frappe")
	def test_add_appends_new_row_with_refreshed_fields(self, mock_frappe):
		mock_frappe.db.get_value.return_value = frappe._dict({
			"item_name": "Lock Plate",
			"description": "Required in this state",
			"stock_uom": "Each",
		})

		rows = [{"item_code": "ASRX-XPKG-9MM-EXT", "qty": 1, "stock_uom": "Each", "source_warehouse": "Stores - TNW"}]
		rules = [
			{
				"rule_name": "CA Lock Plate",
				"substitutions": [{"action": "Add", "to_item": "LOCK-PLATE", "qty": 1}],
			}
		]

		changes = apply(rows, rules)

		self.assertEqual(len(rows), 2)
		new_row = rows[-1]
		self.assertEqual(new_row["item_code"], "LOCK-PLATE")
		self.assertEqual(new_row["item_name"], "Lock Plate")
		self.assertEqual(new_row["qty"], 1)
		self.assertEqual(new_row["stock_uom"], "Each")
		self.assertEqual(new_row["source_warehouse"], "Stores - TNW")
		self.assertEqual(len(changes), 1)
		self.assertEqual(changes[0]["action"], "Add")

	@_PATCH_GETTEXT
	@patch("ffl_manager.compliance.engine.frappe")
	def test_add_missing_item_fails_clearly(self, mock_frappe, _mock_gettext=None):
		mock_frappe.db.get_value.return_value = None
		mock_frappe.throw.side_effect = Exception("boom")

		rows = [{"item_code": "ASRX-XPKG-9MM-EXT", "qty": 1}]
		rules = [
			{
				"rule_name": "Bad Add",
				"substitutions": [{"action": "Add", "to_item": "DOES-NOT-EXIST", "qty": 1}],
			}
		]

		with self.assertRaises(Exception):
			apply(rows, rules)
		mock_frappe.throw.assert_called_once()


class TestApplyMultipleRules(unittest.TestCase):
	@patch("ffl_manager.compliance.engine.frappe")
	def test_disabled_rule_never_reaches_apply_is_a_caller_concern(self, mock_frappe):
		# apply() itself doesn't know about "enabled" - that's filtered by
		# get_rules()/_rule_applies() before rules reach apply(). Simulate a
		# caller that already filtered a disabled rule out.
		mock_frappe.db.get_value.return_value = frappe._dict({
			"item_name": "9mm Standard Mag",
			"description": "",
			"stock_uom": "Each",
		})
		rows = [{"item_code": "ASRX-XPKG-9MM-EXT", "qty": 1, "stock_uom": "Each"}]

		changes = apply(rows, [])  # disabled rule excluded upstream

		self.assertEqual(changes, [])
		self.assertEqual(rows[0]["item_code"], "ASRX-XPKG-9MM-EXT")


class TestApplyRowFilter(unittest.TestCase):
	"""row_filter lets a caller (e.g. the Stock Entry hook) restrict
	substitutions to a subset of rows - e.g. outgoing raw-material rows,
	never the incoming finished-good row on the same Stock Entry."""

	def _rows(self):
		return [
			{"item_code": "ASRX-XPKG-9MM-EXT", "qty": 1, "s_warehouse": "Stores - TNW", "t_warehouse": None},
			{"item_code": "FG-PISTOL-9MM", "qty": 1, "s_warehouse": None, "t_warehouse": "FG - TNW"},
		]

	@staticmethod
	def _is_outgoing(row):
		return bool(row.get("s_warehouse")) and not row.get("t_warehouse")

	@patch("ffl_manager.compliance.engine.frappe")
	def test_replace_only_touches_rows_matching_filter(self, mock_frappe):
		mock_frappe.db.get_value.return_value = frappe._dict({
			"item_name": "9mm Standard Mag",
			"description": "",
			"stock_uom": "Each",
		})
		rows = self._rows()
		rules = [
			{
				"rule_name": "WA Mag Swap",
				"substitutions": [
					{"action": "Replace", "from_item": "ASRX-XPKG-9MM-EXT", "to_item": "ASRX-XPKG-9MM-STN"}
				],
			}
		]

		changes = apply(rows, rules, row_filter=self._is_outgoing)

		self.assertEqual(rows[0]["item_code"], "ASRX-XPKG-9MM-STN")
		self.assertEqual(rows[1]["item_code"], "FG-PISTOL-9MM")  # finished good untouched
		self.assertEqual(len(changes), 1)

	@patch("ffl_manager.compliance.engine.frappe")
	def test_replace_targeting_a_filtered_out_item_is_a_no_op(self, mock_frappe):
		rows = self._rows()
		rules = [
			{
				"rule_name": "No Touch Finished Good",
				"substitutions": [
					{"action": "Replace", "from_item": "FG-PISTOL-9MM", "to_item": "FG-PISTOL-9MM-OTHER"}
				],
			}
		]

		changes = apply(rows, rules, row_filter=self._is_outgoing)

		self.assertEqual(changes, [])
		self.assertEqual(rows[1]["item_code"], "FG-PISTOL-9MM")
		mock_frappe.db.get_value.assert_not_called()


if __name__ == "__main__":
	unittest.main()
