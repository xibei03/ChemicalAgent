"""三种反应器的差别全在这张表里，别处不按反应器类型分支。

操作类型字符串见台账 H15；可挂的反应类型见 H16、H31（Gibbs 反应器用纯自由能最小化，不挂反应集）；
热模式只列验证过的组合（台账“对工具契约的影响”第二节），其余组合抛 E_UNSUPPORTED（R5）。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import HeatMode, ReactionKind, ReactorType


@dataclass(frozen=True)
class ReactorKind:
    """一种反应器在 HYSYS 里的写法。"""

    operation_type: str
    type_name: str
    reaction_kind: ReactionKind | None
    heat_modes: frozenset[HeatMode]


REACTOR_KINDS: Mapping[ReactorType, ReactorKind] = MappingProxyType(
    {
        ReactorType.CONVERSION: ReactorKind(
            operation_type="ConversionReactorOp",
            type_name="conversionreactorop",
            reaction_kind=ReactionKind.CONVERSION,
            heat_modes=frozenset({HeatMode.SPECIFIED_OUTLET_TEMPERATURE, HeatMode.ADIABATIC}),
        ),
        ReactorType.EQUILIBRIUM: ReactorKind(
            operation_type="EquilibriumReactorOp",
            type_name="equilibriumreactorop",
            reaction_kind=ReactionKind.EQUILIBRIUM,
            heat_modes=frozenset(HeatMode),
        ),
        ReactorType.GIBBS: ReactorKind(
            operation_type="GibbsReactorOp",
            type_name="gibbsreactorop",
            reaction_kind=None,
            heat_modes=frozenset({HeatMode.SPECIFIED_OUTLET_TEMPERATURE, HeatMode.ADIABATIC}),
        ),
    }
)


def kind_of(reactor_type: ReactorType) -> ReactorKind:
    """反应器类型对应的写法；PFR、CSTR 目前没有，抛 E_UNSUPPORTED。"""
    kind = REACTOR_KINDS.get(reactor_type)
    if kind is None:
        raise ReactorAgentError(
            ErrorCode.UNSUPPORTED, f"HYSYS Backend 暂不支持 {reactor_type.value} 反应器"
        )
    return kind


def reactor_type_of(type_name: str) -> ReactorType | None:
    """HYSYS 读回的 TypeName 对应的反应器类型；不是这三种反应器时是 None。"""
    for reactor_type, kind in REACTOR_KINDS.items():
        if kind.type_name == type_name:
            return reactor_type
    return None
