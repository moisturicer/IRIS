import json

import pytest

from testing.timings import from_junit, load_timings


def test_junit_aggregates_methods_and_parametrized_tests(tmp_path):
    path = tmp_path / "report.xml"
    path.write_text('<testsuites><testsuite>'
                    '<testcase classname="apps.ai.tests.test_example.SomeTests" name="test_a[1]" time="2"/>'
                    '<testcase classname="apps.ai.tests.test_example" name="test_b" time="3"/>'
                    '</testsuite></testsuites>')
    assert from_junit([path]) == {"apps/ai/tests/test_example.py": 5}
    with pytest.raises(ValueError, match="duplicate"):
        from_junit([path, path])


@pytest.mark.parametrize("value", [-1, True, "2", float("nan"), float("inf")])
def test_invalid_weights_refused(tmp_path, value):
    path = tmp_path / "timings.json"
    path.write_text(json.dumps({"apps/test_a.py": value}))
    with pytest.raises(ValueError):
        load_timings(path)


def test_junit_refuses_xml_entities(tmp_path):
    from defusedxml.common import DefusedXmlException

    path = tmp_path / "hostile.xml"
    path.write_text('<!DOCTYPE testsuites [<!ENTITY secret SYSTEM "file:///etc/passwd">]>'
                    '<testsuites>&secret;</testsuites>')
    with pytest.raises(DefusedXmlException):
        from_junit([path])
