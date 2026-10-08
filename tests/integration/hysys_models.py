"""集成测试用的三个模型：每个模型是一串工具调用（步骤），按台账里的调用序列排列。

这里手写步骤，等价于阶段 1B 的 Recipe 要编译出来的东西。测试只通过 ToolExecutor 执行这些步骤。
参照值来自计划 §17，不是 HYSYS 的输出。
"""

from dataclasses import dataclass

from pydantic import BaseModel

from reactor_agent.spec.enums import (
    HeatMode,
    PropertyPackage,
    ReactionPhase,
    ReactorType,
    SpecVariable,
    StreamKind,
    ToolName,
)
from reactor_agent.spec.snapshot import ModelSnapshot, StreamSnapshot
from reactor_agent.spec.tool_args import (
    CompositionEntry,
    ConversionReaction,
    EnsureReactionArgs,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureStreamArgs,
    EnsureThermoArgs,
    EquilibriumReaction,
    FeedConditions,
    ReadSnapshotArgs,
    SetSpecArgs,
    SolveArgs,
    StoichiometricTerm,
)

KMOL_PER_NM3 = 1.0 / 22.414


@dataclass(frozen=True)
class Step:
    """一次工具调用。"""

    tool: ToolName
    args: BaseModel


def terms(*pairs: tuple[str, float]) -> tuple[StoichiometricTerm, ...]:
    return tuple(StoichiometricTerm(component=name, coefficient=value) for name, value in pairs)


def composition(**fractions: float) -> tuple[CompositionEntry, ...]:
    return tuple(CompositionEntry(component=name, mole_fraction=f) for name, f in fractions.items())


def thermo(*components: str) -> Step:
    args = EnsureThermoArgs(components=components, property_package=PropertyPackage.PENG_ROBINSON)
    return Step(ToolName.BASIS_ENSURE_THERMO, args)


def reaction(name: str, definition: ConversionReaction | EquilibriumReaction) -> Step:
    return Step(ToolName.BASIS_ENSURE_REACTION, EnsureReactionArgs(name=name, reaction=definition))


def reaction_set(name: str, *reactions: str) -> Step:
    return Step(
        ToolName.BASIS_ENSURE_REACTION_SET, EnsureReactionSetArgs(name=name, reactions=reactions)
    )


def feed(name: str, conditions: FeedConditions) -> Step:
    return Step(
        ToolName.FLOWSHEET_ENSURE_STREAM, EnsureStreamArgs(name=name, conditions=conditions)
    )


def stream(name: str) -> Step:
    return Step(ToolName.FLOWSHEET_ENSURE_STREAM, EnsureStreamArgs(name=name))


def energy(name: str) -> Step:
    return Step(
        ToolName.FLOWSHEET_ENSURE_STREAM, EnsureStreamArgs(name=name, kind=StreamKind.ENERGY)
    )


def reactor(**fields: object) -> Step:
    return Step(ToolName.FLOWSHEET_ENSURE_REACTOR, EnsureReactorArgs.model_validate(fields))


def outlet_temperature(reactor_name: str, temperature_c: float) -> Step:
    args = SetSpecArgs(
        object_name=reactor_name, variable=SpecVariable.OUTLET_TEMPERATURE_C, value=temperature_c
    )
    return Step(ToolName.FLOWSHEET_SET_SPEC, args)


SOLVE = Step(ToolName.SOLVER_SOLVE, SolveArgs())
SNAPSHOT = Step(ToolName.MODEL_READ_SNAPSHOT, ReadSnapshotArgs())


# ------------------------------------------------------------------ 转化反应器（计划 §17.2）
TOLUENE_COMPONENTS = ("Toluene", "Benzene", "p-Xylene", "m-Xylene", "o-Xylene")
CONVERSION_FRACTIONS = {
    "Toluene": 0.500,
    "Benzene": 0.250,
    "p-Xylene": 0.060,
    "m-Xylene": 0.130,
    "o-Xylene": 0.060,
}
CONVERSION_TOLERANCE = 0.001


def conversion_model() -> list[Step]:
    """甲苯歧化：2 甲苯 → 苯 + 0.24 对 + 0.52 间 + 0.24 邻二甲苯，转化率 50%，绝热。"""
    disproportionation = ConversionReaction(
        stoichiometry=terms(
            ("Toluene", -2.0),
            ("Benzene", 1.0),
            ("p-Xylene", 0.24),
            ("m-Xylene", 0.52),
            ("o-Xylene", 0.24),
        ),
        base_component="Toluene",
        conversion_percent=50.0,
    )
    conditions = FeedConditions(
        temperature_c=380.0,
        pressure_bar=25.0,
        composition=composition(Toluene=1.0),
        mass_flow_kg_h=10000.0,
    )
    return [
        thermo(*TOLUENE_COMPONENTS),
        reaction("Rxn-1", disproportionation),
        reaction_set("RxnSet-1", "Rxn-1"),
        feed("Feed", conditions),
        stream("Vap"),
        stream("Liq"),
        reactor(
            name="CRV-100",
            reactor_type=ReactorType.CONVERSION,
            feeds=("Feed",),
            vapour_product="Vap",
            liquid_product="Liq",
            reaction_set="RxnSet-1",
            heat_mode=HeatMode.ADIABATIC,
        ),
        SOLVE,
        SNAPSHOT,
    ]


# ------------------------------------------------------------------ 平衡反应器（计划 §17.1）
STEAM_COMPONENTS = ("Methane", "H2O", "CO", "CO2", "Hydrogen")
# 出口温度 -> (湿基摩尔分率, 出口总摩尔流量 kmol/h)
EQUILIBRIUM_REFERENCE = {
    710.0: ({"Methane": 0.094, "H2O": 0.381, "Hydrogen": 0.411, "CO": 0.047, "CO2": 0.067}, 4800.0),
    600.0: ({"Methane": 0.162, "H2O": 0.499, "Hydrogen": 0.269, "CO": 0.012, "CO2": 0.058}, 4305.0),
}
EQUILIBRIUM_TOLERANCE = 0.02


def steam_feed_conditions() -> FeedConditions:
    return FeedConditions(
        temperature_c=520.0,
        pressure_bar=13.5,
        composition=composition(Methane=0.2703, H2O=0.7297),
        molar_flow_kmol_h=3700.0,
    )


def equilibrium_model(temperatures_c: tuple[float, ...] = (710.0, 600.0)) -> list[Step]:
    """甲烷蒸汽重整：两个平衡反应，Keq 来自 Gibbs 自由能，依次在各个出口温度下求解并读回。"""
    reforming = EquilibriumReaction(
        stoichiometry=terms(("Methane", -1.0), ("H2O", -1.0), ("CO", 1.0), ("Hydrogen", 3.0))
    )
    shift = EquilibriumReaction(
        stoichiometry=terms(("CO", -1.0), ("H2O", -1.0), ("CO2", 1.0), ("Hydrogen", 1.0))
    )
    steps = [
        thermo(*STEAM_COMPONENTS),
        reaction("Rxn-1", reforming),
        reaction("Rxn-2", shift),
        reaction_set("RxnSet-1", "Rxn-1", "Rxn-2"),
        feed("Feed", steam_feed_conditions()),
        stream("Vap"),
        stream("Liq"),
        energy("Q-100"),
        reactor(
            name="ERV-100",
            reactor_type=ReactorType.EQUILIBRIUM,
            feeds=("Feed",),
            vapour_product="Vap",
            liquid_product="Liq",
            energy_stream="Q-100",
            reaction_set="RxnSet-1",
            heat_mode=HeatMode.SPECIFIED_OUTLET_TEMPERATURE,
        ),
    ]
    for temperature_c in temperatures_c:
        steps += [outlet_temperature("ERV-100", temperature_c), SOLVE, SNAPSHOT]
    return steps


# ---------------------------------------------------- 含固体碳的气化（计划 §17.3，D14 方案 A）
GASIFICATION_COMPONENTS = ("Carbon", "H2O", "CO", "Hydrogen", "CO2", "Methane")
GASIFICATION_FEED_KMOL_H = 80000.0 * KMOL_PER_NM3
CARBON_MOLE_FRACTION = 0.710
OUTLET_TEMPERATURE_C = 1400.0
CO_YIELD_RANGE = (0.38, 0.42)
REFERENCE_GAS_FRACTIONS = {"CO": 0.500, "Hydrogen": 0.482}
REFERENCE_UNREACTED_CARBON_KMOL_H = 1491.0
GAS_FRACTION_TOLERANCE = 0.02
CARBON_AMOUNT_TOLERANCE = 0.05


def gasification_model() -> list[Step]:
    """两段式：转化反应器按限量反应物算 C + H2O → CO + H2，Gibbs 反应器再算气相平衡。

    库里的固体碳在 Gibbs 反应器里算不对（台账 L24、L25），所以第一段用转化反应器，未反应的碳从
    第一台的液相出料旁路。进料是碳水浆料（重液相），转化反应的反应相用合并相。
    """
    gasification = ConversionReaction(
        stoichiometry=terms(("Carbon", -1.0), ("H2O", -1.0), ("CO", 1.0), ("Hydrogen", 1.0)),
        base_component="H2O",
        conversion_percent=100.0,
        phase=ReactionPhase.COMBINED,
    )
    conditions = FeedConditions(
        temperature_c=40.0,
        pressure_bar=40.0,
        composition=composition(Carbon=CARBON_MOLE_FRACTION, H2O=1.0 - CARBON_MOLE_FRACTION),
        molar_flow_kmol_h=GASIFICATION_FEED_KMOL_H,
    )
    return [
        thermo(*GASIFICATION_COMPONENTS),
        reaction("Rxn-1", gasification),
        reaction_set("RxnSet-1", "Rxn-1"),
        feed("Feed", conditions),
        stream("Gas-1"),
        stream("Carbon-1"),
        energy("Q-1"),
        reactor(
            name="CRV-100",
            reactor_type=ReactorType.CONVERSION,
            feeds=("Feed",),
            vapour_product="Gas-1",
            liquid_product="Carbon-1",
            energy_stream="Q-1",
            reaction_set="RxnSet-1",
            heat_mode=HeatMode.SPECIFIED_OUTLET_TEMPERATURE,
        ),
        stream("Gas-2"),
        stream("Liq-2"),
        energy("Q-2"),
        reactor(
            name="GBR-100",
            reactor_type=ReactorType.GIBBS,
            feeds=("Gas-1",),
            vapour_product="Gas-2",
            liquid_product="Liq-2",
            energy_stream="Q-2",
            heat_mode=HeatMode.SPECIFIED_OUTLET_TEMPERATURE,
        ),
        outlet_temperature("CRV-100", OUTLET_TEMPERATURE_C),
        outlet_temperature("GBR-100", OUTLET_TEMPERATURE_C),
        SOLVE,
        SNAPSHOT,
    ]


# ------------------------------------------------------------------ 读结果
def stream_of(snapshot: ModelSnapshot, name: str) -> StreamSnapshot:
    return next(item for item in snapshot.streams if item.name == name)


def fractions_of(stream_snapshot: StreamSnapshot) -> dict[str, float]:
    """物流各组分的摩尔分率；不应该有读不到的值。"""
    values = {item.name: item.mole_fraction for item in stream_snapshot.components}
    assert None not in values.values(), values
    return {name: value for name, value in values.items() if value is not None}


def molar_flows_of(stream_snapshot: StreamSnapshot) -> dict[str, float]:
    values = {item.name: item.molar_flow_kmol_h for item in stream_snapshot.components}
    assert None not in values.values(), values
    return {name: value for name, value in values.items() if value is not None}
