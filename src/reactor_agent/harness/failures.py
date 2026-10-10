"""执行器里失败的几种来源：一次工具调用失败、规格没有通过 Recipe 的规则、需要用户补充信息。

都是 ReactorAgentError，所以 step() 里一个 except 就能接住；这里只是把它们造得带够诊断需要的信息，
并由 terminal_status 决定中止时的终态。
"""

from collections.abc import Sequence

from pydantic import BaseModel

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import TaskStatus, ToolName
from reactor_agent.spec.results import Issue, issue_details
from reactor_agent.spec.tool_results import ToolError

MAX_ARGUMENTS_CHARS = 400


class ToolStepError(ReactorAgentError):
    """一次工具调用失败。比领域错误多带工具名和入参，诊断要用。"""

    def __init__(self, tool: ToolName, args: BaseModel, error: ToolError) -> None:
        super().__init__(error.code, error.message, error.details)
        self.tool = tool.value
        text = args.model_dump_json()
        shortened = text if len(text) <= MAX_ARGUMENTS_CHARS else text[:MAX_ARGUMENTS_CHARS] + "…"
        self.arguments = shortened


def rule_error(issues: Sequence[Issue]) -> ReactorAgentError:
    """规格没有通过 Recipe 的规则。只要有一条是“不支持”，就是系统做不了，不是用户改一改能解决的。"""
    unsupported = any(issue.code is ErrorCode.UNSUPPORTED for issue in issues)
    code = ErrorCode.UNSUPPORTED if unsupported else ErrorCode.RULE
    return ReactorAgentError(code, f"规格有 {len(issues)} 处不合规", issue_details(issues))


def _for_the_user(issue: Issue) -> Issue:
    """给用户看的问题：系统做不了的原因标明，不能让用户改完再撞上它。"""
    if issue.user_fixable or issue.code is not ErrorCode.UNSUPPORTED:
        return issue
    return issue.model_copy(update={"message": f"系统暂不支持：{issue.message}"})


class NeedsInputError(ReactorAgentError):
    """缺少关键信息，或者用户给的信息有问题：要用户补充或更正，不是系统出错。终态是 NEEDS_INPUT。

    给用户看的是用户可更正的问题，加上系统做不了的原因（另外的是 LLM 写法上的问题，用户用不上）。
    """

    def __init__(self, issues: Sequence[Issue]) -> None:
        fixable = [issue for issue in issues if issue.user_fixable]
        shown = [
            issue for issue in issues if issue.user_fixable or issue.code is ErrorCode.UNSUPPORTED
        ]
        code = fixable[0].code if fixable else ErrorCode.RULE
        message = f"需要用户补充或确认 {len(fixable)} 处信息"
        super().__init__(code, message, issue_details([_for_the_user(i) for i in shown]))


def terminal_status(error: ReactorAgentError) -> TaskStatus:
    """中止时的终态：要用户补充是 NEEDS_INPUT，系统做不了是 UNSUPPORTED，其余是 FAILED。"""
    if isinstance(error, NeedsInputError):
        return TaskStatus.NEEDS_INPUT
    return TaskStatus.UNSUPPORTED if error.code is ErrorCode.UNSUPPORTED else TaskStatus.FAILED
