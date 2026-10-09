"""执行器里失败的两种来源：工具调用失败时带上的工具名和入参，规格没有通过规则时用哪个错误码。"""

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.harness.failures import MAX_ARGUMENTS_CHARS, ToolStepError, rule_error
from reactor_agent.spec.enums import ToolName
from reactor_agent.spec.results import make_issue
from reactor_agent.spec.tool_args import EnsureCaseArgs, EnsureThermoArgs
from reactor_agent.spec.tool_results import ToolError


def failed(code: ErrorCode = ErrorCode.NOT_FOUND) -> ToolError:
    return ToolError.of(code, "没有找到", {"Methane": "没有这个组分"})


def test_a_tool_step_error_is_a_domain_error_that_remembers_the_tool_and_its_arguments():
    args = EnsureCaseArgs(path="C:/runs/t/work/working-1.hsc")
    error = ToolStepError(ToolName.CASE_ENSURE, args, failed())
    assert isinstance(error, ReactorAgentError)
    assert (error.code, error.message) == (ErrorCode.NOT_FOUND, "没有找到")
    assert dict(error.details) == {"Methane": "没有这个组分"}
    assert error.tool == "case.ensure"
    assert "working-1.hsc" in error.arguments


def test_long_arguments_are_cut_with_an_ellipsis_so_the_diagnosis_is_not_mistaken_for_complete():
    components = tuple(f"Component-{n}" for n in range(200))
    args = EnsureThermoArgs(components=components, property_package="peng_robinson")
    error = ToolStepError(ToolName.BASIS_ENSURE_THERMO, args, failed())
    assert len(error.arguments) == MAX_ARGUMENTS_CHARS + 1
    assert error.arguments.endswith("…")


def test_short_arguments_are_kept_whole():
    args = EnsureCaseArgs(path="C:/a.hsc")
    error = ToolStepError(ToolName.CASE_ENSURE, args, failed())
    assert error.arguments == args.model_dump_json()
    assert not error.arguments.endswith("…")


def test_rule_issues_are_a_rule_error_listed_by_field():
    error = rule_error(
        [make_issue(ErrorCode.RULE, "feeds", "a"), make_issue(ErrorCode.RULE, "cases", "b")]
    )
    assert error.code is ErrorCode.RULE
    assert dict(error.details) == {"feeds": "a", "cases": "b"}
    assert "2 处" in error.message


def test_one_unsupported_issue_makes_the_whole_error_unsupported():
    error = rule_error(
        [make_issue(ErrorCode.RULE, "feeds", "a"), make_issue(ErrorCode.UNSUPPORTED, "x", "b")]
    )
    assert error.code is ErrorCode.UNSUPPORTED
    assert dict(error.details) == {"feeds": "a", "x": "b"}
