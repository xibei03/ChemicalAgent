"""检查结论的构造和数值的写法。"""

import pytest

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.enums import CheckId, CheckSeverity
from reactor_agent.spec.results import (
    CHECK_TITLES,
    MAX_PROBLEMS_SHOWN,
    check_result,
    describe,
    issue_details,
    make_issue,
)


class TestDescribe:
    def test_unknown_value_is_written_as_unknown(self):
        assert describe(None) == "未知"

    def test_values_keep_six_significant_digits(self):
        assert describe(1234.56789) == "1234.57"
        assert describe(0.000123456789) == "0.000123457"
        assert describe(0.0) == "0"


class TestIssueDetails:
    def test_issues_about_different_fields_are_listed_by_field(self):
        issues = [
            make_issue(ErrorCode.RULE, "feeds", "a"),
            make_issue(ErrorCode.RULE, "cases", "b"),
        ]
        assert issue_details(issues) == {"feeds": "a", "cases": "b"}

    def test_several_issues_about_one_field_are_joined_not_overwritten(self):
        issues = [
            make_issue(ErrorCode.RULE, "components", "缺 CO"),
            make_issue(ErrorCode.RULE, "feeds", "没有水"),
            make_issue(ErrorCode.RULE, "components", "缺氢气"),
        ]
        assert issue_details(issues) == {"components": "缺 CO；缺氢气", "feeds": "没有水"}

    def test_no_issues_give_no_details(self):
        assert issue_details([]) == {}


class TestCheckResult:
    def test_no_problems_means_passed_and_reports_what_was_found(self):
        result = check_result(CheckId.SOLVED, "期望", "找到的", [])
        assert result.passed
        assert result.severity is CheckSeverity.FATAL
        assert (result.expected, result.actual) == ("期望", "找到的")
        assert CHECK_TITLES[CheckId.SOLVED] in result.message

    def test_problems_mean_failed_and_are_listed(self):
        result = check_result(CheckId.FEEDS, "期望", "找到的", ["温度不对", "压力不对"])
        assert not result.passed
        assert result.actual == "温度不对；压力不对"
        assert "2 处" in result.message
        assert "温度不对" in result.message

    def test_only_the_first_problems_are_listed_and_the_rest_are_counted(self):
        problems = [f"问题{n}" for n in range(MAX_PROBLEMS_SHOWN + 3)]
        result = check_result(CheckId.STRUCTURE, "期望", "", problems)
        assert "问题0" in result.actual
        assert f"问题{MAX_PROBLEMS_SHOWN}" not in result.actual
        assert "另有 3 处" in result.actual

    def test_exactly_the_limit_does_not_say_there_are_more(self):
        problems = [f"问题{n}" for n in range(MAX_PROBLEMS_SHOWN)]
        assert "另有" not in check_result(CheckId.STRUCTURE, "期望", "", problems).actual

    @pytest.mark.parametrize("check_id", list(CheckId))
    def test_every_check_has_a_title(self, check_id):
        assert CHECK_TITLES[check_id]
