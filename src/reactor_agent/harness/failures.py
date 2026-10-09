"""执行器里失败的两种来源：一次工具调用失败，或者规格没有通过 Recipe 的规则。

都是 ReactorAgentError，所以 step() 里一个 except 就能接住；这里只是把它们造得带够诊断需要的信息。
"""

from collections.abc import Sequence

from pydantic import BaseModel

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import ToolName
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
