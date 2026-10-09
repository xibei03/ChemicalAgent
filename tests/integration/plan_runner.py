"""按 Recipe 编译出的计划执行：基础和流程图一次，然后每个工况改规定值、求解、读快照。

这是阶段 1C 执行器主流程的雏形，只用于测试：不重试、不恢复，任何一步失败就让测试失败。
"""

from reactor_agent.recipes import recipe_for
from reactor_agent.spec.components import ComponentTable
from reactor_agent.spec.enums import ToolName
from reactor_agent.spec.model_spec import ModelSpec, OperatingCase
from reactor_agent.spec.plan import BuildPlan
from reactor_agent.spec.snapshot import ModelSnapshot
from reactor_agent.spec.tool_args import ReadSnapshotArgs, SolveArgs
from reactor_agent.tools.registry import ToolExecutor

SOLVE_TIMEOUT_S = 120.0


def execute(executor: ToolExecutor, tool: str, args: object) -> object:
    """调一个工具，失败就让测试失败并带上错误详情。返回结果里的数据。"""
    result = executor.call(tool, args)
    assert result.ok, f"{tool} 失败：{result.error}"
    return result.data


def compile_plan(spec: ModelSpec, table: ComponentTable) -> BuildPlan:
    recipe = recipe_for(spec.reactor_type)
    assert recipe is not None
    assert recipe.rules(spec, table) == ()
    return recipe.compile(spec, table)


def run_cases(
    executor: ToolExecutor, spec: ModelSpec, plan: BuildPlan
) -> list[tuple[OperatingCase, ModelSnapshot]]:
    """建模一次，再逐个工况求解并读回快照。Case 必须已经新建好。"""
    for step in plan.steps:
        if step.case_name is None:
            execute(executor, step.tool, step.args)
    snapshots = []
    for case in spec.cases:
        for step in plan.case_steps(case.name):
            execute(executor, step.tool, step.args)
        execute(executor, ToolName.SOLVER_SOLVE, SolveArgs(timeout_s=SOLVE_TIMEOUT_S))
        snapshot = execute(executor, ToolName.MODEL_READ_SNAPSHOT, ReadSnapshotArgs())
        assert isinstance(snapshot, ModelSnapshot)
        snapshots.append((case, snapshot))
    return snapshots
