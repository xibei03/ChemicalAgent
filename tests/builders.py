"""单元测试的构造器：按计划造一份“正确的”快照，测试再一处一处把它改坏。

三个场景（转化、平衡、两段式气化）的出料用反应进度手算，不经过任何求解器，所以元素和质量都守恒，
数值可以手工核对。fixture 在 conftest.py 里，下一阶段的执行器测试也复用它们。
"""

import copy
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

from reactor_agent.recipes import recipe_for
from reactor_agent.spec.components import (
    ComponentTable,
    feed_molar_flow_kmol_h,
    load_component_table,
)
from reactor_agent.spec.enums import ComponentPhase, ObjectState
from reactor_agent.spec.loading import read_document
from reactor_agent.spec.model_spec import ModelSpec, OperatingCase, load_model_spec
from reactor_agent.spec.plan import BuildPlan, energy_stream_names, material_stream_names
from reactor_agent.spec.results import CheckContext, Provenance
from reactor_agent.spec.snapshot import (
    ComponentInfo,
    EnergyStreamSnapshot,
    ModelSnapshot,
    ObjectStatus,
    ReactionSetSnapshot,
    ReactionSnapshot,
    ReactorSnapshot,
    SolveStatus,
    StreamComponent,
    StreamSnapshot,
    ThermoSnapshot,
)
from reactor_agent.spec.tool_args import (
    EnsureReactionArgs,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureThermoArgs,
)

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "evals" / "golden_specs"
TABLE_FILE = REPO / "config" / "components.yaml"

# 流量（kmol/h）按组分，出料的定义：名字 → （温度 °C，组分流量）
Outlets = Mapping[str, tuple[float, Mapping[str, float]]]


@cache
def component_table() -> ComponentTable:
    return load_component_table(TABLE_FILE)


def golden_spec(name: str) -> ModelSpec:
    return load_model_spec(GOLDEN / f"{name}.yaml")


def stream_snapshot(
    spec: ModelSpec,
    name: str,
    flows: Mapping[str, float],
    temperature_c: float,
    pressure_bar: float,
) -> StreamSnapshot:
    """按组分摩尔流量造一股物流：分率和质量流量由分子量算出，没有流量的组分是 0。"""
    weights = {e.name: e.molecular_weight_kg_per_kmol for e in component_table().components}
    total = sum(flows.values())
    items = tuple(
        StreamComponent(
            name=component,
            mole_fraction=flows.get(component, 0.0) / total if total else 0.0,
            molar_flow_kmol_h=flows.get(component, 0.0),
            mass_flow_kg_h=flows.get(component, 0.0) * weights[component],
        )
        for component in spec.components
    )
    return StreamSnapshot(
        name=name,
        temperature_c=temperature_c,
        pressure_bar=pressure_bar,
        molar_flow_kmol_h=total,
        mass_flow_kg_h=sum(item.mass_flow_kg_h or 0.0 for item in items),
        vapour_fraction=1.0 if total else None,
        heavy_liquid_fraction=0.0,
        components=items,
    )


def feed_flows(spec: ModelSpec) -> dict[str, float]:
    """规格里第一股进料各组分的摩尔流量（kmol/h）。"""
    feed = spec.feeds[0]
    total = feed_molar_flow_kmol_h(feed, component_table())
    return {item.component: total * item.mole_fraction for item in feed.composition}


@dataclass(frozen=True)
class Scenario:
    """一个场景：规格、计划、当前工况和一份正确的快照。"""

    spec: ModelSpec
    plan: BuildPlan
    case: OperatingCase
    snapshot: ModelSnapshot

    @property
    def table(self) -> ComponentTable:
        return component_table()

    @property
    def context(self) -> CheckContext:
        return CheckContext(
            spec=self.spec,
            case=self.case,
            plan=self.plan,
            components=self.table,
            snapshot=self.snapshot,
        )

    def with_spec(self, spec: ModelSpec) -> "Scenario":
        """换一份规格，快照和计划不变：用来检查结果检查是拿快照和规格比，而不是和计划自己比。"""
        return replace(self, spec=spec)

    def with_reactor(self, index: int, **changes: object) -> "Scenario":
        """把第 index 台反应器的某些字段改掉。"""
        reactors = tuple(
            r.model_copy(update=changes) if i == index else r
            for i, r in enumerate(self.snapshot.reactors)
        )
        return self.with_snapshot(reactors=reactors)

    def with_snapshot(self, **changes: object) -> "Scenario":
        return replace(self, snapshot=self.snapshot.model_copy(update=changes))

    def with_stream(self, name: str, **changes: object) -> "Scenario":
        """把一股物流的某些字段改掉。"""
        streams = tuple(
            s.model_copy(update=changes) if s.name == name else s for s in self.snapshot.streams
        )
        return self.with_snapshot(streams=streams)

    def with_component(self, stream: str, component: str, **changes: object) -> "Scenario":
        """把一股物流里某个组分的某些字段改掉。"""
        old = next(s for s in self.snapshot.streams if s.name == stream)
        items = tuple(
            c.model_copy(update=changes) if c.name == component else c for c in old.components
        )
        return self.with_stream(stream, components=items)

    def with_flows(self, stream: str, **changes: float) -> "Scenario":
        """改掉一股物流里某些组分的摩尔流量，总量、分率和质量流量跟着重算，物流内部仍然一致。"""
        old = self.snapshot.stream(stream)
        assert old is not None
        flows = {c.name: c.molar_flow_kmol_h or 0.0 for c in old.components}
        flows.update(changes)
        new = stream_snapshot(
            self.spec, stream, flows, old.temperature_c or 0.0, old.pressure_bar or 0.0
        )
        return self.with_snapshot(
            streams=tuple(new if s.name == stream else s for s in self.snapshot.streams)
        )

    def without_stream(self, name: str) -> "Scenario":
        return self.with_snapshot(streams=tuple(s for s in self.snapshot.streams if s.name != name))


def _snapshot(
    spec: ModelSpec, plan: BuildPlan, outlets: Outlets, duties: Mapping[str, float]
) -> ModelSnapshot:
    table = component_table()
    streams = []
    for name in material_stream_names(plan):
        if name in outlets:
            temperature_c, flows = outlets[name]
            streams.append(
                stream_snapshot(spec, name, flows, temperature_c, spec.feeds[0].pressure_bar)
            )
        else:
            feed = spec.feeds[0]
            flows = feed_flows(spec)
            streams.append(
                stream_snapshot(spec, name, flows, feed.temperature_c, feed.pressure_bar)
            )
    thermo_args = plan.args_of(EnsureThermoArgs)[0]
    entries = {e.name: e for e in table.components}
    thermo = ThermoSnapshot(
        fluid_package="Basis-1",
        property_package=thermo_args.property_package,
        components=tuple(
            ComponentInfo(
                name=n,
                formula=entries[n].formula,
                is_solid=entries[n].phase is ComponentPhase.SOLID,
            )
            for n in thermo_args.components
        ),
    )
    reactors = tuple(
        ReactorSnapshot(
            name=r.name,
            reactor_type=r.reactor_type,
            feeds=r.feeds,
            vapour_product=r.vapour_product,
            liquid_product=r.liquid_product,
            energy_stream=r.energy_stream,
            reaction_set=r.reaction_set,
            pressure_drop_bar=r.pressure_drop_bar,
        )
        for r in plan.args_of(EnsureReactorArgs)
    )
    objects = (
        *(ObjectStatus(name=s.name, type_name="stream", state=ObjectState.OK) for s in streams),
        *(ObjectStatus(name=r.name, type_name="reactor", state=ObjectState.OK) for r in reactors),
    )
    return ModelSnapshot(
        case_path=Path("case.hsc"),
        thermo=thermo,
        reactions=tuple(
            ReactionSnapshot(name=a.name, definition=a.reaction, balance_error_kg_per_kmol=0.0)
            for a in plan.args_of(EnsureReactionArgs)
        ),
        reaction_sets=tuple(
            ReactionSetSnapshot(name=a.name, reactions=a.reactions, attached_to_fluid_package=True)
            for a in plan.args_of(EnsureReactionSetArgs)
        ),
        streams=tuple(streams),
        energy_streams=tuple(
            EnergyStreamSnapshot(name=n, duty_kw=duties[n]) for n in energy_stream_names(plan)
        ),
        reactors=reactors,
        solve=SolveStatus(is_solving=False, objects=objects),
    )


def build_scenario(
    spec: ModelSpec, outlets: Outlets, duties: Mapping[str, float], case_name: str | None = None
) -> Scenario:
    recipe = recipe_for(spec.reactor_type)
    assert recipe is not None
    plan = recipe.compile(spec, component_table())
    case = next(c for c in spec.cases if case_name in (None, c.name))
    return Scenario(spec, plan, case, _snapshot(spec, plan, outlets, duties))


def conversion_scenario(converted: float = 0.5) -> Scenario:
    """甲苯歧化：甲苯转化 converted（默认 50%，等于规格），反应进度是转化量的一半，绝热。"""
    spec = golden_spec("toluene_conversion")
    toluene = feed_flows(spec)["Toluene"]
    extent = converted / 2 * toluene
    vapour = {
        "Toluene": (1 - converted) * toluene,
        "Benzene": extent,
        "p-Xylene": 0.24 * extent,
        "m-Xylene": 0.52 * extent,
        "o-Xylene": 0.24 * extent,
    }
    outlets = {"Vap": (378.6, vapour), "Liq": (378.6, {})}
    return build_scenario(spec, outlets, {})


STEAM_REFORMING_EXTENTS = (550.0, 200.0)
STEAM_REFORMING_DUTY_KW = 39989.0


def equilibrium_scenario(case_name: str = "T710", spec: ModelSpec | None = None) -> Scenario:
    """蒸汽重整：两个反应的进度是 550 和 200 kmol/h，所以甲烷转化率 55%，出口总量 4800 kmol/h。"""
    spec = spec or golden_spec("smr_equilibrium")
    feed = feed_flows(spec)
    reforming, shift = STEAM_REFORMING_EXTENTS
    vapour = {
        "Methane": feed["Methane"] - reforming,
        "H2O": feed["H2O"] - reforming - shift,
        "CO": reforming - shift,
        "Hydrogen": 3 * reforming + shift,
        "CO2": shift,
    }
    case = next(c for c in spec.cases if c.name == case_name)
    # 规定热负荷的工况没有给出口温度，用一个合理的值
    temperature = 710.0 if case.outlet_temperature_c is None else case.outlet_temperature_c
    duty = STEAM_REFORMING_DUTY_KW if case.duty_kw is None else case.duty_kw
    outlets = {"Vap": (temperature, vapour), "Liq": (temperature, {})}
    return build_scenario(spec, outlets, {"Q-100": duty}, case_name)


GASIFICATION_METHANATION = 0.05
GASIFICATION_SHIFT = 0.02


def gasification_scenario(spec: ModelSpec | None = None) -> Scenario:
    """两段式：水限量，第一段水全部变成 CO 和氢气（进度 W）；第二段气相再有两个反应。"""
    spec = spec or golden_spec("slurry_gibbs")
    feed = feed_flows(spec)
    water = feed["H2O"]
    methanation = GASIFICATION_METHANATION * water
    shift = GASIFICATION_SHIFT * water
    first_gas = {"CO": water, "Hydrogen": water}
    second_gas = {
        "CO": water - methanation - shift,
        "Hydrogen": water - 3 * methanation + shift,
        "Methane": methanation,
        "H2O": methanation - shift,
        "CO2": shift,
    }
    temperature = 1400.0
    outlets = {
        "Vap-1": (temperature, first_gas),
        "Liq-1": (temperature, {"Carbon": feed["Carbon"] - water}),
        "Vap-2": (temperature, second_gas),
        "Liq-2": (temperature, {}),
    }
    return build_scenario(spec, outlets, {"Q-1": 60000.0, "Q-2": 25000.0})


def provenance() -> Provenance:
    return Provenance(
        simulator_version="Aspen HYSYS V15",
        case_path=Path("case.hsc"),
        read_at=datetime(2026, 10, 9, 8, 0, tzinfo=UTC),
        spec_hash="0" * 64,
    )


def golden_data(name: str) -> dict[str, Any]:
    """黄金规格文件的原始内容（字典），测试改掉几个字段再校验，用来造各种规格。"""
    return copy.deepcopy(read_document(GOLDEN / f"{name}.yaml"))


def spec_from(data: Mapping[str, Any]) -> ModelSpec:
    return ModelSpec.model_validate(data)
