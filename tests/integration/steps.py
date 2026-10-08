"""执行一串工具调用步骤，每一步都必须成功。"""

from hysys_models import Step

from reactor_agent.spec.tool_results import ToolResult
from reactor_agent.tools.registry import ToolExecutor


def describe(step: Step, result: ToolResult) -> str:
    """失败时说明是哪一步、什么错，包括 HYSYS 弹窗的文字。"""
    error = result.error
    return f"{step.tool} 失败：{error.code} {error.message} {dict(error.details)}" if error else ""


def run_steps(executor: ToolExecutor, steps: list[Step]) -> list[ToolResult]:
    """依次执行步骤，任何一步失败就让测试失败并带上错误详情。"""
    results = []
    for step in steps:
        result = executor.call(step.tool, step.args)
        assert result.ok, describe(step, result)
        results.append(result)
    return results
