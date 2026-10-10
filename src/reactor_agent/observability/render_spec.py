"""把规格和建模计划渲染成人能读的文字：干跑（--dry-run）打印的就是这些。

纯函数，输出文本，不打印。数字都是代码从规格里取出来格式化的，不经过 LLM。
"""

from collections.abc import Mapping
from types import MappingProxyType

from reactor_agent.spec.enums import HeatMode, KeqSource
from reactor_agent.spec.model_spec import ConversionMetric, ModelSpec, RatioMetric, YieldMetric
from reactor_agent.spec.plan import BuildPlan, BuildStep
from reactor_agent.spec.selection import REACTOR_NAMES
from reactor_agent.spec.tool_args import (
    ConversionReaction,
    EnsureReactionArgs,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureStreamArgs,
    EnsureThermoArgs,
    ReactionDefinition,
)

INDENT = "  "
HEAT_MODE_TEXT: Mapping[HeatMode, str] = MappingProxyType(
    {
        HeatMode.SPECIFIED_OUTLET_TEMPERATURE: "规定出口温度",
        HeatMode.ADIABATIC: "绝热",
        HeatMode.SPECIFIED_DUTY: "规定热负荷",
    }
)


def _g(value: float) -> str:
    return f"{value:.6g}"


def _reaction_text(reaction: ReactionDefinition) -> str:
    left = " + ".join(
        f"{_g(-t.coefficient)} {t.component}" for t in reaction.stoichiometry if t.coefficient < 0
    )
    right = " + ".join(
        f"{_g(t.coefficient)} {t.component}" for t in reaction.stoichiometry if t.coefficient > 0
    )
    if isinstance(reaction, ConversionReaction):
        base, percent = reaction.base_component, _g(reaction.conversion_percent)
        detail = f"转化反应，基准组分 {base}，转化率 {percent}%"
    elif reaction.keq_source is KeqSource.FIXED_K:
        detail = f"平衡反应，固定 K = {_g(reaction.equilibrium_constant or 0.0)}"
    else:
        detail = "平衡反应，平衡常数由 Gibbs 自由能计算"
    return f"{left} → {right}（{detail}）"


def _metric_text(metric: ConversionMetric | YieldMetric | RatioMetric) -> str:
    if isinstance(metric, ConversionMetric):
        return f"{metric.component} 的转化率"
    if isinstance(metric, YieldMetric):
        return f"{metric.product} 的收率（相对 {metric.basis} 的进料）"
    return f"{metric.numerator} / {metric.denominator} 的摩尔流量比"


def render_model_spec(spec: ModelSpec) -> str:
    """换算后的规格：反应器、物性包、组分、进料、反应、压降、工况、指标。"""
    lines = [
        "规格（已换算成规范单位：°C、bar 绝压、kmol/h 或 kg/h、摩尔分率）：",
        f"{INDENT}反应器：{REACTOR_NAMES[spec.reactor_type]}；物性包：{spec.property_package.value}；"
        f"热模式：{HEAT_MODE_TEXT[spec.heat_mode]}；压降：{_g(spec.pressure_drop_bar)} bar",
        f"{INDENT}组分：{'、'.join(spec.components)}",
    ]
    for feed in spec.feeds:
        flow = (
            f"{_g(feed.molar_flow_kmol_h)} kmol/h"
            if feed.molar_flow_kmol_h is not None
            else f"{_g(feed.mass_flow_kg_h or 0.0)} kg/h"
        )
        fractions = "、".join(f"{c.component} {c.mole_fraction:.4f}" for c in feed.composition)
        lines.append(
            f"{INDENT}进料 {feed.name}：{_g(feed.temperature_c)} °C，{_g(feed.pressure_bar)} bar，"
            f"{flow}；摩尔分率 {fractions}"
        )
    for index, reaction in enumerate(spec.reactions, start=1):
        lines.append(f"{INDENT}反应 {index}：{_reaction_text(reaction)}")
    for case in spec.cases:
        if case.outlet_temperature_c is not None:
            rule = f"出口温度 {_g(case.outlet_temperature_c)} °C"
        elif case.duty_kw is not None:
            rule = f"热负荷 {_g(case.duty_kw)} kW"
        else:
            rule = "没有规定（出口温度是结果）"
        lines.append(f"{INDENT}工况 {case.name}：{rule}")
    lines.extend(f"{INDENT}待求指标：{_metric_text(metric)}" for metric in spec.metrics)
    return "\n".join(lines)


def render_assumptions(spec: ModelSpec) -> str:
    """假设清单：每条是针对哪个字段、取了什么值、为什么。"""
    if not spec.assumptions:
        return "假设：没有"
    lines = [f"假设（{len(spec.assumptions)} 条）："]
    lines.extend(
        f"{INDENT}{item.id} [{item.field_path}] {item.value.rstrip('。')}。{item.reason}"
        for item in spec.assumptions
    )
    return "\n".join(lines)


def _step_text(step: BuildStep) -> str:
    args = step.args
    if isinstance(args, EnsureThermoArgs):
        return f"组分 {'、'.join(args.components)}，物性包 {args.property_package.value}"
    if isinstance(args, EnsureReactionArgs):
        return f"{args.name}：{_reaction_text(args.reaction)}"
    if isinstance(args, EnsureReactionSetArgs):
        return f"{args.name} 含 {'、'.join(args.reactions)}"
    if isinstance(args, EnsureStreamArgs):
        return f"{args.name}（{args.kind.value}）"
    if isinstance(args, EnsureReactorArgs):
        return (
            f"{args.name}（{REACTOR_NAMES[args.reactor_type]}）："
            f"{'、'.join(args.feeds)} → {args.vapour_product}、{args.liquid_product}"
        )
    return f"{args.object_name} 的 {args.variable.value} = {_g(args.value)}"


def render_plan(plan: BuildPlan) -> str:
    """将要执行的建模步骤（不含连接、新建 Case、求解、读快照和保存，那些每种反应器都一样）。"""
    lines = [f"建模步骤（{len(plan.steps)} 步）："]
    for step in plan.steps:
        where = f" [{step.case_name}]" if step.case_name else ""
        lines.append(f"{INDENT}{step.number:>2} {step.tool.value}{where}：{_step_text(step)}")
    return "\n".join(lines)
