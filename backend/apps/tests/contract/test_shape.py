"""
The structure comparer's own rules (IR-915). Pure: runs without a database.

Each test states what a screen reading the response would experience, because
that is the reason a change fails or is only reported.
"""

import json
import unittest

from apps.tests.contract.shape import SAMPLE_ITEMS, compare, sample_of, shape_of


def diff(before, after):
    return compare(shape_of(before), shape_of(after))


class ShapeOfTests(unittest.TestCase):
    def test_scalars(self):
        self.assertEqual(shape_of("a"), "string")
        self.assertEqual(shape_of(3), "number")
        self.assertEqual(shape_of(3.5), "number")
        self.assertEqual(shape_of(True), "boolean")  # not "number": bool is an int in Python
        self.assertEqual(shape_of(None), "null")

    def test_an_object_and_a_list(self):
        self.assertEqual(
            shape_of({"id": 1, "tags": ["a"]}),
            {"object": {"id": "number", "tags": {"array": "string"}}},
        )

    def test_an_empty_list_has_no_item_structure(self):
        self.assertEqual(shape_of([]), {"array": None})

    def test_items_that_leave_a_field_null_are_typed_by_the_ones_that_fill_it(self):
        shape = shape_of([{"note": None, "id": 1}, {"note": "x", "id": 2}, {"id": 3}])
        self.assertEqual(shape, {"array": {
            "object": {"note": "string", "id": "number"}, "optional": ["note"],
        }})

    def test_items_of_different_kinds_are_mixed(self):
        self.assertEqual(shape_of([1, "a"]), {"array": {"mixed": ["number", "string"]}})

    def test_a_value_that_is_not_json_is_refused(self):
        with self.assertRaises(TypeError):
            shape_of(object())


class CompareTests(unittest.TestCase):
    def test_the_same_structure_with_other_values_is_no_change(self):
        self.assertFalse(diff({"id": 1, "title": "A", "tags": ["x"]}, {"id": 9, "title": "B", "tags": []}))

    def test_a_removed_field_fails_and_names_the_field(self):
        result = diff({"id": 1, "title": "A"}, {"id": 1})
        self.assertEqual(result.breaking, ["$.title: removed"])

    def test_a_renamed_field_is_a_removal_and_an_addition(self):
        result = diff({"title": "A"}, {"name": "A"})
        self.assertEqual(result.breaking, ["$.title: removed"])
        self.assertEqual(result.added, ["$.name: added"])

    def test_a_field_that_changes_kind_fails_and_says_how(self):
        result = diff({"count": 1}, {"count": "1"})
        self.assertEqual(result.breaking, ["$.count: was number, now string"])

    def test_a_field_that_becomes_null_fails(self):
        result = diff({"title": "A"}, {"title": None})
        self.assertEqual(result.breaking, ["$.title: was string, now null"])

    def test_a_field_that_was_null_in_the_sample_checks_only_that_the_key_exists(self):
        self.assertFalse(diff({"note": None}, {"note": "now filled"}))
        self.assertEqual(diff({"note": None}, {}).breaking, ["$.note: removed"])

    def test_an_added_field_is_reported_and_does_not_fail(self):
        result = diff({"id": 1}, {"id": 1, "extra": True})
        self.assertEqual(result.breaking, [])
        self.assertEqual(result.added, ["$.extra: added"])

    def test_a_field_inside_a_list_is_named_with_its_path(self):
        result = diff({"results": [{"id": 1, "title": "A"}]}, {"results": [{"id": 1}]})
        self.assertEqual(result.breaking, ["$.results[].title: removed"])

    def test_an_empty_sample_list_says_nothing_about_its_items(self):
        self.assertFalse(diff({"results": []}, {"results": [{"id": 1}]}))

    def test_an_empty_answer_says_nothing_either(self):
        self.assertFalse(diff({"results": [{"id": 1}]}, {"results": []}))

    def test_an_object_that_becomes_a_list_fails(self):
        result = diff({"a": {"b": 1}}, {"a": [1]})
        self.assertEqual(result.breaking, ["$.a: was an object, now a list"])

    def test_a_field_with_two_recorded_kinds_accepts_either(self):
        before = {"entry": [{"available": True, "record": {"id": 1}}, {"available": False}]}
        self.assertFalse(diff(before, {"entry": [{"available": False}]}))

    def test_a_field_with_two_recorded_kinds_refuses_a_third(self):
        result = diff({"x": [1, "a"]}, {"x": [True]})
        self.assertEqual(len(result.breaking), 1)
        self.assertIn("$.x[]", result.breaking[0])


class SampleOfTests(unittest.TestCase):
    def test_long_lists_are_cut_to_a_few_items_at_any_depth(self):
        sample = sample_of({"results": list(range(10)), "inner": {"rows": [{"n": i} for i in range(9)]}})
        self.assertEqual(len(sample["results"]), SAMPLE_ITEMS)
        self.assertEqual(len(sample["inner"]["rows"]), SAMPLE_ITEMS)

    def test_the_sample_is_plain_json(self):
        payload = {"a": [1, None, {"b": True}]}
        self.assertEqual(json.loads(json.dumps(sample_of(payload))), payload)


if __name__ == "__main__":
    unittest.main()
