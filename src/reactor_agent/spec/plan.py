"""BuildPlan：Recipe 从 ModelSpec 编译出来的、有序的建模步骤。

计划里只有建模步骤：Basis、流程图、各工况的规定。连接 HYSYS、新建 Case、求解、读快照、保存，
是每种反应器都一样的动作，由执行器直接调用，不进计划。工具名、阶段和编号都由 assemble_plan
按入参的类型填写，Recipe 只管产出入参。
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Self, TypeVar

from pydantic import BaseModel, Field, model_validator

from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import StepPhase, StreamKind, ToolName
from reactor_agent.spec.tool_args import (
    EnsureReactionArgs,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureStreamArgs,
    EnsureThermoArgs,
    SetSpecArgs,
)

BasisArgs = EnsureThermoArgs | EnsureReactionArgs | EnsureReactionSetArgs
FlowsheetArgs = EnsureStreamArgs | EnsureReactorArgs
StepArgs = BasisArgs | FlowsheetArgs | SetSpecArgs
ArgsT = TypeVar("ArgsT", bound=BaseModel)

# 每种入参对应的工具和阶段。计划里只能出现这六种步骤。
STEP_TOOLS: Mapping[type[BaseModel], tuple[ToolName, StepPhase]] = MappingProxyType(
    {
        EnsureThermoArgs: (ToolName.BASIS_ENSURE_THERMO, StepPhase.BASIS),
        EnsureReactionArgs: (ToolName.BASIS_ENSURE_REACTION, StepPhase.BASIS),
        EnsureReactionSetArgs: (ToolName.BASIS_ENSURE_REACTION_SET, StepPhase.BASIS),
        EnsureStreamArgs: (ToolName.FLOWSHEET_ENSURE_STREAM, StepPhase.FLOWSHEET),
        EnsureReactorArgs: (ToolName.FLOWSHEET_ENSURE_REACTOR, StepPhase.FLOWSHEET),
        SetSpecArgs: (ToolName.FLOWSHEET_SET_SPEC, StepPhase.CASE),
    }
)
PHASE_ORDER = (StepPhase.BASIS, StepPhase.FLOWSHEET, StepPhase.CASE)


class BuildStep(FrozenModel):
    """计划里的一步：编号、工具、入参，以及它属于哪个阶段（工况阶段的步骤带工况名）。"""

    number: int = Field(ge=1)
    tool: ToolName
    args: StepArgs
    phase: StepPhase
    case_name: str | None = None

    @model_validator(mode="after")
    def _tool_phase_and_args_agree(self) -> Self:
        if STEP_TOOLS.get(type(self.args)) != (self.tool, self.phase):
            raise ValueError(
                f"第 {self.number} 步：{type(self.args).__name__} 不是"
                f"{self.phase.value} 阶段的工具 {self.tool.value} 的入参"
            )
        if (self.case_name is not None) != (self.phase is StepPhase.CASE):
            raise ValueError(f"第 {self.number} 步：只有工况阶段的步骤带工况名")
        return self


class BuildPlan(FrozenModel):
    """一串有序的建模步骤：先 Basis，再流程图，最后是各个工况。"""

    steps: tuple[BuildStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _steps_are_numbered_and_ordered(self) -> Self:
        if [step.number for step in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("步骤编号必须从 1 开始连续递增")
        order = [PHASE_ORDER.index(step.phase) for step in self.steps]
        if order != sorted(order):
            raise ValueError("步骤必须按 Basis、流程图、工况的顺序排列")
        return self

    def args_of(self, kind: type[ArgsT]) -> tuple[ArgsT, ...]:
        """计划里某一种入参的全部步骤，按计划的顺序。"""
        return tuple(step.args for step in self.steps if isinstance(step.args, kind))

    def case_steps(self, case_name: str) -> tuple[BuildStep, ...]:
        """某个工况的步骤。没有需要改的规定值时（比如绝热）是空的。"""
        return tuple(step for step in self.steps if step.case_name == case_name)


def _step(number: int, args: StepArgs, case_name: str | None) -> BuildStep:
    tool, phase = STEP_TOOLS[type(args)]
    return BuildStep(number=number, tool=tool, args=args, phase=phase, case_name=case_name)


@dataclass(frozen=True)
class CaseSpecs:
    """一个工况要改的规定值：对每台反应器各一步，绝热的工况没有。"""

    name: str
    specs: tuple[SetSpecArgs, ...]


def assemble_plan(
    basis: Sequence[BasisArgs], flowsheet: Sequence[FlowsheetArgs], cases: Sequence[CaseSpecs]
) -> BuildPlan:
    """把 Basis、流程图和各工况的入参排成计划，编号从 1 开始。"""
    ordered: list[tuple[StepArgs, str | None]] = [(args, None) for args in (*basis, *flowsheet)]
    ordered += [(args, case.name) for case in cases for args in case.specs]
    return BuildPlan(steps=tuple(_step(n, a, c) for n, (a, c) in enumerate(ordered, start=1)))


def _streams(plan: BuildPlan, kind: StreamKind) -> tuple[EnsureStreamArgs, ...]:
    return tuple(args for args in plan.args_of(EnsureStreamArgs) if args.kind is kind)


def material_stream_names(plan: BuildPlan) -> tuple[str, ...]:
    """计划里全部物料流的名字（进料、中间物流和出料）。"""
    return tuple(args.name for args in _streams(plan, StreamKind.MATERIAL))


def energy_stream_names(plan: BuildPlan) -> tuple[str, ...]:
    """计划里全部能流的名字。"""
    return tuple(args.name for args in _streams(plan, StreamKind.ENERGY))


def system_feed_names(plan: BuildPlan) -> tuple[str, ...]:
    """系统的进料：带规定（温度、压力、组成）的物料流，顺序与规格里的进料一致。"""
    return tuple(a.name for a in _streams(plan, StreamKind.MATERIAL) if a.conditions is not None)


def _unconsumed(plan: BuildPlan, products: Iterable[str]) -> tuple[str, ...]:
    consumed = {name for reactor in plan.args_of(EnsureReactorArgs) for name in reactor.feeds}
    return tuple(name for name in products if name not in consumed)


def system_vapour_outlets(plan: BuildPlan) -> tuple[str, ...]:
    """系统的气相出料：反应器的气相出料里没有再被别的反应器当作进料的。"""
    reactors = plan.args_of(EnsureReactorArgs)
    return _unconsumed(plan, (reactor.vapour_product for reactor in reactors))


def system_liquid_outlets(plan: BuildPlan) -> tuple[str, ...]:
    """系统的液相出料（含固体）：反应器的液相出料里没有再被别的反应器当作进料的。"""
    reactors = plan.args_of(EnsureReactorArgs)
    return _unconsumed(plan, (reactor.liquid_product for reactor in reactors))


def system_outlet_names(plan: BuildPlan) -> tuple[str, ...]:
    """系统的全部出料：先气相，后液相。物料守恒和派生指标都按它们合计。"""
    return (*system_vapour_outlets(plan), *system_liquid_outlets(plan))
