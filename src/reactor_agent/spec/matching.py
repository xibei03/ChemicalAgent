"""“已有的对象和期望的配置是否一致”的纯函数。

ensure_* 工具靠它们决定返回“未改变”还是 E_CONFLICT，创建之后的读回比对也用它们。每个函数返回
人能读的差异描述，空元组表示一致。写成独立的纯函数，是因为它们出错会导致幂等失效或误报冲突。
"""

import math
from collections.abc import Mapping

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.snapshot import (
    ReactionSetSnapshot,
    ReactorSnapshot,
    StreamSnapshot,
    ThermoSnapshot,
)
from reactor_agent.spec.tool_args import (
    ConversionReaction,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureThermoArgs,
    EquilibriumReaction,
    FeedConditions,
    ReactionDefinition,
)

# HYSYS 会在质量守恒检查时微调最后一个计量系数（台账 H9：1.0 变 1.00005）。
STOICHIOMETRY_TOLERANCE = 1e-3
# 写进去再读回来的物理量，只有换算和浮点表示的误差。
VALUE_REL_TOLERANCE = 1e-6
VALUE_ABS_TOLERANCE = 1e-6


def _close(first: float | None, second: float | None, tolerance: float) -> bool:
    if first is None or second is None:
        return first is second
    return math.isclose(first, second, rel_tol=tolerance, abs_tol=tolerance)


def _value_close(first: float | None, second: float | None) -> bool:
    return _close(first, second, VALUE_REL_TOLERANCE)


def _difference(what: str, existing: object, wanted: object) -> str:
    return f"{what}：已有 {existing}，期望 {wanted}"


def _stoichiometry(reaction: ReactionDefinition) -> Mapping[str, float]:
    return {term.component: term.coefficient for term in reaction.stoichiometry}


def _stoichiometry_differences(
    existing: ReactionDefinition, wanted: ReactionDefinition
) -> list[str]:
    have, want = _stoichiometry(existing), _stoichiometry(wanted)
    if have.keys() != want.keys():
        return [_difference("反应式的组分", sorted(have), sorted(want))]
    return [
        _difference(f"{name} 的计量系数", have[name], want[name])
        for name in want
        if not _close(have[name], want[name], STOICHIOMETRY_TOLERANCE)
    ]


def _conversion_differences(existing: ConversionReaction, wanted: ConversionReaction) -> list[str]:
    found = []
    if existing.base_component != wanted.base_component:
        found.append(_difference("基准组分", existing.base_component, wanted.base_component))
    if not _value_close(existing.conversion_percent, wanted.conversion_percent):
        found.append(_difference("转化率", existing.conversion_percent, wanted.conversion_percent))
    return found


def _equilibrium_differences(
    existing: EquilibriumReaction, wanted: EquilibriumReaction
) -> list[str]:
    found = []
    if existing.keq_source != wanted.keq_source:
        found.append(_difference("平衡常数来源", existing.keq_source, wanted.keq_source))
    if not _value_close(existing.equilibrium_constant, wanted.equilibrium_constant):
        found.append(
            _difference("平衡常数", existing.equilibrium_constant, wanted.equilibrium_constant)
        )
    return found


def reaction_differences(
    existing: ReactionDefinition, wanted: ReactionDefinition
) -> tuple[str, ...]:
    """已有的反应与期望的反应有哪些不同。计量系数在 STOICHIOMETRY_TOLERANCE 内算相同。"""
    if existing.kind != wanted.kind:
        return (_difference("反应类型", existing.kind, wanted.kind),)
    found = _stoichiometry_differences(existing, wanted)
    if existing.phase != wanted.phase:
        found.append(_difference("反应相", existing.phase, wanted.phase))
    if isinstance(existing, ConversionReaction) and isinstance(wanted, ConversionReaction):
        found += _conversion_differences(existing, wanted)
    if isinstance(existing, EquilibriumReaction) and isinstance(wanted, EquilibriumReaction):
        found += _equilibrium_differences(existing, wanted)
    return tuple(found)


def thermo_differences(existing: ThermoSnapshot, wanted: EnsureThermoArgs) -> tuple[str, ...]:
    """已有的流体包与期望的组分表和物性包有哪些不同。组分表的顺序也要一致。"""
    found = []
    names = tuple(component.name for component in existing.components)
    if names != wanted.components:
        found.append(_difference("组分表", names, wanted.components))
    if existing.property_package != wanted.property_package:
        found.append(_difference("物性包", existing.property_package, wanted.property_package))
    return tuple(found)


def reaction_set_differences(
    existing: ReactionSetSnapshot, wanted: EnsureReactionSetArgs
) -> tuple[str, ...]:
    """已有的反应集与期望的成员有哪些不同。成员的顺序无关，但必须已经挂到流体包。"""
    found = []
    if set(existing.reactions) != set(wanted.reactions):
        found.append(_difference("反应集的成员", existing.reactions, wanted.reactions))
    if not existing.attached_to_fluid_package:
        found.append("反应集没有挂到流体包")
    return tuple(found)


def _composition_differences(existing: StreamSnapshot, wanted: FeedConditions) -> list[str]:
    have = {item.name: item.mole_fraction for item in existing.components}
    want = {entry.component: entry.mole_fraction for entry in wanted.composition}
    return [
        _difference(f"{name} 的摩尔分率", have.get(name), want.get(name, 0.0))
        for name in sorted(have.keys() | want.keys())
        if not _close(have.get(name), want.get(name, 0.0), VALUE_ABS_TOLERANCE)
    ]


def stream_differences(existing: StreamSnapshot, wanted: FeedConditions) -> tuple[str, ...]:
    """已有的物流与期望的规定（温度、压力、组成、流量）有哪些不同。"""
    found = []
    if not _value_close(existing.temperature_c, wanted.temperature_c):
        found.append(_difference("温度 °C", existing.temperature_c, wanted.temperature_c))
    if not _value_close(existing.pressure_bar, wanted.pressure_bar):
        found.append(_difference("压力 bar", existing.pressure_bar, wanted.pressure_bar))
    found += _composition_differences(existing, wanted)
    if wanted.molar_flow_kmol_h is not None:
        if not _value_close(existing.molar_flow_kmol_h, wanted.molar_flow_kmol_h):
            found.append(
                _difference("摩尔流量 kmol/h", existing.molar_flow_kmol_h, wanted.molar_flow_kmol_h)
            )
    elif not _value_close(existing.mass_flow_kg_h, wanted.mass_flow_kg_h):
        found.append(_difference("质量流量 kg/h", existing.mass_flow_kg_h, wanted.mass_flow_kg_h))
    return tuple(found)


def reactor_differences(existing: ReactorSnapshot, wanted: EnsureReactorArgs) -> tuple[str, ...]:
    """已有的反应器与期望的类型、连接、反应集和压降有哪些不同。进料的顺序无关。"""
    found = []
    if existing.reactor_type != wanted.reactor_type:
        found.append(_difference("反应器类型", existing.reactor_type, wanted.reactor_type))
    if set(existing.feeds) != set(wanted.feeds):
        found.append(_difference("进料", existing.feeds, wanted.feeds))
    for what, have, want in (
        ("气相出料", existing.vapour_product, wanted.vapour_product),
        ("液相出料", existing.liquid_product, wanted.liquid_product),
        ("能流", existing.energy_stream, wanted.energy_stream),
        ("反应集", existing.reaction_set, wanted.reaction_set),
    ):
        if have != want:
            found.append(_difference(what, have, want))
    if not _value_close(existing.pressure_drop_bar, wanted.pressure_drop_bar):
        found.append(_difference("压降 bar", existing.pressure_drop_bar, wanted.pressure_drop_bar))
    return tuple(found)


def require_match(code: ErrorCode, subject: str, differences: tuple[str, ...]) -> None:
    """有差异就抛 ReactorAgentError：消息说明是哪个对象、第一处差异，细节列出全部差异。"""
    if differences:
        message = f"{subject}与期望不一致：{differences[0]}"
        raise ReactorAgentError(code, message, {"differences": "；".join(differences)})
