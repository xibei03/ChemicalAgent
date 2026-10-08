"""model.read_snapshot 的结果：从仿真软件读回的模型状态。

读不到的值是 None。仿真软件的空值哨兵数不会离开 Backend。
"""

from pathlib import Path

from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import ObjectState, PropertyPackage, ReactorType
from reactor_agent.spec.tool_args import ReactionDefinition


class ObjectStatus(FrozenModel):
    """流程图里一个对象的求解状态。"""

    name: str
    type_name: str
    state: ObjectState


class SolveStatus(FrozenModel):
    """整个流程图的求解状态。"""

    is_solving: bool
    objects: tuple[ObjectStatus, ...]

    @property
    def solved(self) -> bool:
        """求解器空闲，有对象，并且没有对象处于未求解、欠规定或错误状态。"""
        healthy = {ObjectState.OK, ObjectState.WARNING}
        return (
            not self.is_solving
            and bool(self.objects)
            and all(item.state in healthy for item in self.objects)
        )


class ComponentInfo(FrozenModel):
    """组分表里的一项。"""

    name: str
    formula: str | None
    is_solid: bool


class ThermoSnapshot(FrozenModel):
    """流体包：物性包和组分表（顺序就是物流组成向量的顺序）。"""

    fluid_package: str
    property_package: PropertyPackage | None
    components: tuple[ComponentInfo, ...]


class ReactionSnapshot(FrozenModel):
    """一个反应。balance_error_kg_per_kmol 是仿真软件算出的质量不守恒量，平衡时为 0。"""

    name: str
    definition: ReactionDefinition
    balance_error_kg_per_kmol: float | None


class ReactionSetSnapshot(FrozenModel):
    """一个反应集：参加反应的成员，以及有没有挂到流体包。"""

    name: str
    reactions: tuple[str, ...]
    attached_to_fluid_package: bool


class StreamComponent(FrozenModel):
    """物流里一个组分的量。"""

    name: str
    mole_fraction: float | None
    molar_flow_kmol_h: float | None
    mass_flow_kg_h: float | None


class StreamSnapshot(FrozenModel):
    """一股物料物流。固体组分在重液相里，按重液相分率和各组分的流量判断它去了哪里。"""

    name: str
    temperature_c: float | None
    pressure_bar: float | None
    molar_flow_kmol_h: float | None
    mass_flow_kg_h: float | None
    vapour_fraction: float | None
    heavy_liquid_fraction: float | None
    components: tuple[StreamComponent, ...]


class EnergyStreamSnapshot(FrozenModel):
    """一股能流。热负荷吸热为正。"""

    name: str
    duty_kw: float | None


class ReactorSnapshot(FrozenModel):
    """一台反应器的类型和连接。没有连接的引用是 None。"""

    name: str
    reactor_type: ReactorType
    feeds: tuple[str, ...]
    vapour_product: str | None
    liquid_product: str | None
    energy_stream: str | None
    reaction_set: str | None
    pressure_drop_bar: float | None


class ModelSnapshot(FrozenModel):
    """整个模型的状态，同时用于步骤读回和结果读取。"""

    case_path: Path
    thermo: ThermoSnapshot | None
    reactions: tuple[ReactionSnapshot, ...]
    reaction_sets: tuple[ReactionSetSnapshot, ...]
    streams: tuple[StreamSnapshot, ...]
    energy_streams: tuple[EnergyStreamSnapshot, ...]
    reactors: tuple[ReactorSnapshot, ...]
    solve: SolveStatus
