"""12 个工具的入参模型。

非法的值在构造模型时就被拒绝，进入 HYSYS 之前不会有脏数据。物理量用规范单位：
°C、bar（绝压）、kmol/h、kg/h、kW。转化率是百分数（和 HYSYS 一致，Backend 不换算）。
可区分的联合类型（反应的定义）是入参模型的一个字段，联合本身不当入参。
"""

import math
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, StringConstraints, field_validator, model_validator

from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import (
    CaseMode,
    ConnectMode,
    HeatMode,
    KeqSource,
    PropertyPackage,
    ReactionKind,
    ReactionPhase,
    ReactorType,
    SpecVariable,
    StreamKind,
)

ABSOLUTE_ZERO_C = -273.15
COMPOSITION_SUM_TOLERANCE = 1e-6
ZERO_TOLERANCE = 1e-12
DEFAULT_SOLVE_TIMEOUT_S = 120.0
MAX_SOLVE_TIMEOUT_S = 600.0
CASE_FILE_SUFFIX = ".hsc"

# 对象名由代码按约定生成（物流、反应、反应器的编号名一类），字符集收窄到 HYSYS 一定接受的。
ObjectName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,59}$")]
# 组分名是 HYSYS 组分库里的规范名，大小写和连字符都要一致。
ComponentName = Annotated[str, StringConstraints(min_length=1, max_length=60)]
TemperatureC = Annotated[float, Field(gt=ABSOLUTE_ZERO_C, allow_inf_nan=False)]
PositiveValue = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
PressureDropBar = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


def check_unique(names: tuple[str, ...], what: str) -> None:
    """名字不能重复，重复就抛 ValueError（用在 pydantic 的校验器里）。"""
    if len(set(names)) != len(names):
        raise ValueError(f"{what}里有重复的名字")


def _check_case_path(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("Case 路径必须是绝对路径")
    if path.suffix.lower() != CASE_FILE_SUFFIX:
        raise ValueError(f"Case 文件的扩展名必须是 {CASE_FILE_SUFFIX}")
    return path


CasePath = Annotated[Path, AfterValidator(_check_case_path)]


class StoichiometricTerm(FrozenModel):
    """反应式里的一项。计量系数为负是反应物，为正是产物，可以是分数。"""

    component: ComponentName
    coefficient: FiniteFloat

    @field_validator("coefficient")
    @classmethod
    def _non_zero(cls, value: float) -> float:
        if math.isclose(value, 0.0, abs_tol=ZERO_TOLERANCE):
            raise ValueError("计量系数不能为零")
        return value


class StoichiometricReaction(FrozenModel):
    """各类反应共有的部分：计量系数和反应发生的相。"""

    stoichiometry: tuple[StoichiometricTerm, ...]
    phase: ReactionPhase = ReactionPhase.VAPOUR

    @field_validator("stoichiometry")
    @classmethod
    def _has_reactants_and_products(
        cls, terms: tuple[StoichiometricTerm, ...]
    ) -> tuple[StoichiometricTerm, ...]:
        check_unique(tuple(term.component for term in terms), "反应式")
        if not any(term.coefficient < 0 for term in terms):
            raise ValueError("反应式里没有反应物（计量系数为负）")
        if not any(term.coefficient > 0 for term in terms):
            raise ValueError("反应式里没有产物（计量系数为正）")
        return terms


class ConversionReaction(StoichiometricReaction):
    """转化反应：基准组分按给定的转化率反应，产物按计量系数的比例生成。"""

    kind: Literal[ReactionKind.CONVERSION] = ReactionKind.CONVERSION
    base_component: ComponentName
    conversion_percent: Annotated[float, Field(gt=0.0, le=100.0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def _base_component_is_a_reactant(self) -> Self:
        reactants = {term.component for term in self.stoichiometry if term.coefficient < 0}
        if self.base_component not in reactants:
            raise ValueError("基准组分必须是反应物（计量系数为负）")
        return self


class EquilibriumReaction(StoichiometricReaction):
    """平衡反应。固定 K 时必须给平衡常数（摩尔分率基准，台账 H10），其他来源不能给。"""

    kind: Literal[ReactionKind.EQUILIBRIUM] = ReactionKind.EQUILIBRIUM
    keq_source: KeqSource = KeqSource.GIBBS_ENERGY
    equilibrium_constant: PositiveValue | None = None

    @model_validator(mode="after")
    def _constant_matches_source(self) -> Self:
        if (self.keq_source is KeqSource.FIXED_K) != (self.equilibrium_constant is not None):
            raise ValueError("固定 K 必须给平衡常数，其他来源不能给")
        return self


ReactionDefinition = Annotated[
    ConversionReaction | EquilibriumReaction, Field(discriminator="kind")
]


class CompositionEntry(FrozenModel):
    """组成里的一项：组分和摩尔分率。"""

    component: ComponentName
    mole_fraction: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]


class FeedConditions(FrozenModel):
    """物流的规定：温度、压力、摩尔分率组成，以及摩尔流量或质量流量（二选一）。"""

    temperature_c: TemperatureC
    pressure_bar: PositiveValue
    composition: tuple[CompositionEntry, ...] = Field(min_length=1)
    molar_flow_kmol_h: PositiveValue | None = None
    mass_flow_kg_h: PositiveValue | None = None

    @field_validator("composition")
    @classmethod
    def _sums_to_one(cls, entries: tuple[CompositionEntry, ...]) -> tuple[CompositionEntry, ...]:
        check_unique(tuple(entry.component for entry in entries), "组成")
        total = math.fsum(entry.mole_fraction for entry in entries)
        if not math.isclose(total, 1.0, abs_tol=COMPOSITION_SUM_TOLERANCE):
            raise ValueError(f"摩尔分率之和应为 1，实际是 {total}")
        return entries

    @model_validator(mode="after")
    def _exactly_one_flow(self) -> Self:
        if (self.molar_flow_kmol_h is None) == (self.mass_flow_kg_h is None):
            raise ValueError("流量要在摩尔流量和质量流量里二选一")
        return self


class ConnectArgs(FrozenModel):
    """session.connect：默认新开一个 HYSYS 实例；接管已有实例只用于调试。"""

    mode: ConnectMode = ConnectMode.LAUNCH
    visible: bool = True


class EnsureCaseArgs(FrozenModel):
    """case.ensure：新建空白 Case 并立刻另存到 path，或者打开已有的文件。"""

    path: CasePath
    mode: CaseMode = CaseMode.NEW


class SaveCaseArgs(FrozenModel):
    """case.save：path 为空时写回当前路径。"""

    path: CasePath | None = None


class CloseCaseArgs(FrozenModel):
    """case.close：save 为真时先保存。"""

    save: bool = False


class EnsureThermoArgs(FrozenModel):
    """basis.ensure_thermo：组分（库里的规范名，顺序固定）和物性包。"""

    components: tuple[ComponentName, ...] = Field(min_length=1)
    property_package: PropertyPackage

    @field_validator("components")
    @classmethod
    def _unique_components(cls, names: tuple[str, ...]) -> tuple[str, ...]:
        check_unique(names, "组分表")
        return names


class EnsureReactionArgs(FrozenModel):
    """basis.ensure_reaction：名称和反应的定义。"""

    name: ObjectName
    reaction: ReactionDefinition


class EnsureReactionSetArgs(FrozenModel):
    """basis.ensure_reaction_set：名称和成员反应，创建后挂到流体包。"""

    name: ObjectName
    reactions: tuple[ObjectName, ...] = Field(min_length=1)

    @field_validator("reactions")
    @classmethod
    def _unique_reactions(cls, names: tuple[str, ...]) -> tuple[str, ...]:
        check_unique(names, "反应集")
        return names


class EnsureStreamArgs(FrozenModel):
    """flowsheet.ensure_stream：物流或能流。出料物流和能流不给规定（conditions 为空）。"""

    name: ObjectName
    kind: StreamKind = StreamKind.MATERIAL
    conditions: FeedConditions | None = None

    @model_validator(mode="after")
    def _energy_stream_has_no_conditions(self) -> Self:
        if self.kind is StreamKind.ENERGY and self.conditions is not None:
            raise ValueError("能流没有温度、压力和组成，热负荷用 flowsheet.set_spec 规定")
        return self


class EnsureReactorArgs(FrozenModel):
    """flowsheet.ensure_reactor：类型、连接、反应集、压降和热模式。

    出口温度和热负荷是工况变量，不在这里，只通过 flowsheet.set_spec 设置。heat_mode 是自洽性声明：
    绝热等价于没有能流，另外两种必须有能流。
    """

    name: ObjectName
    reactor_type: ReactorType
    feeds: tuple[ObjectName, ...] = Field(min_length=1)
    vapour_product: ObjectName
    liquid_product: ObjectName
    energy_stream: ObjectName | None = None
    reaction_set: ObjectName | None = None
    pressure_drop_bar: PressureDropBar = 0.0
    heat_mode: HeatMode

    @model_validator(mode="after")
    def _connections_are_consistent(self) -> Self:
        check_unique((*self.feeds, self.vapour_product, self.liquid_product), "反应器的物流")
        if (self.heat_mode is HeatMode.ADIABATIC) != (self.energy_stream is None):
            raise ValueError("绝热的反应器不接能流，其他热模式必须接能流")
        return self


class SetSpecArgs(FrozenModel):
    """flowsheet.set_spec：规定反应器的一个工况变量，单位由变量名决定。"""

    object_name: ObjectName
    variable: SpecVariable
    value: FiniteFloat

    @model_validator(mode="after")
    def _temperature_is_above_absolute_zero(self) -> Self:
        if self.variable is SpecVariable.OUTLET_TEMPERATURE_C and self.value <= ABSOLUTE_ZERO_C:
            raise ValueError("温度必须高于绝对零度")
        return self


class SolveArgs(FrozenModel):
    """solver.solve：等待求解完成的上限。"""

    timeout_s: Annotated[float, Field(gt=0.0, le=MAX_SOLVE_TIMEOUT_S)] = DEFAULT_SOLVE_TIMEOUT_S


class ReadSnapshotArgs(FrozenModel):
    """model.read_snapshot：本阶段只做不带参数的全量读取。"""
