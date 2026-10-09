"""Basis 和物流的前置检查：用假的 COM 对象，不需要 HYSYS。

检查两处审查修出来的行为：流体包已存在但 Basis 还没结束要报冲突；物流的组分不对时先校验、
不留下一股空物流。
"""

from types import SimpleNamespace

import pytest

from reactor_agent.backends.hysys_com.streams import ensure_stream
from reactor_agent.backends.hysys_com.thermo import component_names, ensure_thermo, read_thermo
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import PropertyPackage, ResultStatus
from reactor_agent.spec.tool_args import (
    CompositionEntry,
    EnsureStreamArgs,
    EnsureThermoArgs,
    FeedConditions,
)


class FakeComponents:
    def __init__(self, names):
        self.Names = tuple(names)

    def Item(self, name):
        return SimpleNamespace(name=name, Formula=f"{name[:2].upper()}8   ", IsSolid=False)


def fake_case(components=("Methane", "H2O"), basis_changing=False, with_package=True):
    package = SimpleNamespace(
        name="Basis-1",
        Components=FakeComponents(components),
        PropertyPackage=SimpleNamespace(TypeName="pengrob"),
    )
    packages = SimpleNamespace(Count=1 if with_package else 0, Item=lambda _index: package)
    manager = SimpleNamespace(FluidPackages=packages, IsChangingBasis=basis_changing)
    return SimpleNamespace(BasisManager=manager)


def thermo_args(*components):
    return EnsureThermoArgs(components=components, property_package=PropertyPackage.PENG_ROBINSON)


def error_of(call):
    with pytest.raises(ReactorAgentError) as caught:
        call()
    return caught.value


def test_existing_thermo_that_matches_is_unchanged():
    outcome = ensure_thermo(fake_case(), thermo_args("Methane", "H2O"))
    assert outcome.status is ResultStatus.UNCHANGED
    assert outcome.data.components == ("Methane", "H2O")


def test_existing_thermo_with_other_components_is_a_conflict():
    error = error_of(lambda: ensure_thermo(fake_case(), thermo_args("Methane", "CO")))
    assert error.code is ErrorCode.CONFLICT


def test_thermo_whose_basis_was_never_ended_is_not_reported_as_unchanged():
    case = fake_case(basis_changing=True)
    error = error_of(lambda: ensure_thermo(case, thermo_args("Methane", "H2O")))
    assert error.code is ErrorCode.CONFLICT
    assert "Basis" in error.message


def test_formula_padding_that_hysys_adds_is_removed():
    thermo = read_thermo(fake_case(("Toluene",)))
    assert thermo.components[0].formula == "TO8"


def test_component_names_keep_the_composition_vector_order():
    assert component_names(fake_case(("H2O", "Methane"))) == ("H2O", "Methane")


def test_component_names_without_a_fluid_package_say_what_to_do_first():
    error = error_of(lambda: component_names(fake_case(with_package=False)))
    assert error.code is ErrorCode.NOT_FOUND
    assert "ensure_thermo" in error.message


class FakeStreams:
    def __init__(self):
        self.Names, self.added = (), []

    def Add(self, name):
        self.added.append(name)
        self.Names = (*self.Names, name)
        return SimpleNamespace(name=name)

    def Item(self, name):
        return SimpleNamespace(name=name)


def feed_conditions(**fractions):
    return FeedConditions(
        temperature_c=25.0,
        pressure_bar=1.0,
        composition=tuple(
            CompositionEntry(component=k, mole_fraction=v) for k, v in fractions.items()
        ),
        molar_flow_kmol_h=10.0,
    )


def test_stream_with_a_component_outside_the_basis_is_rejected_before_anything_is_created():
    flowsheet = SimpleNamespace(MaterialStreams=FakeStreams(), EnergyStreams=FakeStreams())
    args = EnsureStreamArgs(name="Feed", conditions=feed_conditions(Water=1.0))
    error = error_of(lambda: ensure_stream(fake_case(), flowsheet, args))
    assert error.code is ErrorCode.COMPONENT_NOT_FOUND
    assert flowsheet.MaterialStreams.added == []


def test_stream_with_the_same_name_as_an_energy_stream_is_a_conflict():
    energy = FakeStreams()
    energy.Add("Q-100")
    flowsheet = SimpleNamespace(MaterialStreams=FakeStreams(), EnergyStreams=energy)
    error = error_of(lambda: ensure_stream(fake_case(), flowsheet, EnsureStreamArgs(name="Q-100")))
    assert error.code is ErrorCode.CONFLICT
    assert flowsheet.MaterialStreams.added == []
