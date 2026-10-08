"""“已有的对象和期望的配置是否一致”的纯函数。它们出错会导致幂等失效或误报冲突。"""

import pytest

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import (
    HeatMode,
    KeqSource,
    PropertyPackage,
    ReactionPhase,
    ReactorType,
)
from reactor_agent.spec.matching import (
    reaction_differences,
    reaction_set_differences,
    reactor_differences,
    require_match,
    stream_differences,
    thermo_differences,
)
from reactor_agent.spec.snapshot import (
    ComponentInfo,
    ReactionSetSnapshot,
    ReactorSnapshot,
    StreamComponent,
    StreamSnapshot,
    ThermoSnapshot,
)
from reactor_agent.spec.tool_args import (
    CompositionEntry,
    ConversionReaction,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureThermoArgs,
    EquilibriumReaction,
    FeedConditions,
    StoichiometricTerm,
)


def terms(*pairs):
    return tuple(StoichiometricTerm(component=c, coefficient=k) for c, k in pairs)


def conversion(**changes):
    values = {
        "stoichiometry": terms(("Toluene", -2.0), ("Benzene", 1.0), ("p-Xylene", 1.0)),
        "base_component": "Toluene",
        "conversion_percent": 50.0,
    }
    return ConversionReaction(**{**values, **changes})


def equilibrium(**changes):
    values = {"stoichiometry": terms(("CO", -1.0), ("H2O", -1.0), ("CO2", 1.0), ("Hydrogen", 1.0))}
    return EquilibriumReaction(**{**values, **changes})


class TestReactions:
    def test_identical_reactions_have_no_difference(self):
        assert reaction_differences(conversion(), conversion()) == ()

    def test_coefficient_nudged_by_hysys_within_tolerance_is_the_same(self):
        nudged = terms(("Toluene", -2.0), ("Benzene", 1.0), ("p-Xylene", 1.00005))
        assert reaction_differences(conversion(stoichiometry=nudged), conversion()) == ()

    def test_coefficient_off_by_more_than_tolerance_is_reported(self):
        other = terms(("Toluene", -2.0), ("Benzene", 1.0), ("p-Xylene", 1.01))
        found = reaction_differences(conversion(stoichiometry=other), conversion())
        assert len(found) == 1
        assert "p-Xylene" in found[0]

    def test_coefficient_order_does_not_matter(self):
        shuffled = terms(("p-Xylene", 1.0), ("Toluene", -2.0), ("Benzene", 1.0))
        assert reaction_differences(conversion(stoichiometry=shuffled), conversion()) == ()

    def test_different_components_are_reported(self):
        other = terms(("Toluene", -2.0), ("Benzene", 1.0), ("m-Xylene", 1.0))
        assert reaction_differences(conversion(stoichiometry=other), conversion())

    def test_different_conversion_is_reported(self):
        found = reaction_differences(conversion(conversion_percent=60.0), conversion())
        assert len(found) == 1
        assert "转化率" in found[0]

    def test_different_base_component_is_reported(self):
        two_reactants = terms(("CO", -1.0), ("H2O", -1.0), ("CO2", 1.0))
        first = conversion(stoichiometry=two_reactants, base_component="CO")
        second = conversion(stoichiometry=two_reactants, base_component="H2O")
        found = reaction_differences(first, second)
        assert len(found) == 1
        assert "基准组分" in found[0]

    def test_different_kinds_are_reported(self):
        found = reaction_differences(equilibrium(), conversion())
        assert len(found) == 1
        assert "类型" in found[0]

    def test_different_phase_is_reported(self):
        assert reaction_differences(conversion(phase=ReactionPhase.COMBINED), conversion())

    def test_equilibrium_source_and_constant_are_compared(self):
        fixed = equilibrium(keq_source=KeqSource.FIXED_K, equilibrium_constant=12.5)
        assert reaction_differences(fixed, equilibrium())
        assert reaction_differences(fixed, fixed) == ()
        other = equilibrium(keq_source=KeqSource.FIXED_K, equilibrium_constant=13.0)
        assert reaction_differences(other, fixed)


class TestThermo:
    existing = ThermoSnapshot(
        fluid_package="Basis-1",
        property_package=PropertyPackage.PENG_ROBINSON,
        components=(
            ComponentInfo(name="Methane", formula="CH4", is_solid=False),
            ComponentInfo(name="H2O", formula="H2O", is_solid=False),
        ),
    )

    def wanted(self, components=("Methane", "H2O")):
        return EnsureThermoArgs(components=components, property_package="peng_robinson")

    def test_same_components_in_same_order_are_the_same(self):
        assert thermo_differences(self.existing, self.wanted()) == ()

    def test_component_order_matters_because_it_is_the_composition_vector_order(self):
        assert thermo_differences(self.existing, self.wanted(("H2O", "Methane")))

    def test_missing_component_is_reported(self):
        assert thermo_differences(self.existing, self.wanted(("Methane", "H2O", "CO")))

    def test_unknown_property_package_is_reported(self):
        unknown = self.existing.model_copy(update={"property_package": None})
        assert thermo_differences(unknown, self.wanted())


class TestReactionSets:
    existing = ReactionSetSnapshot(
        name="RxnSet-1", reactions=("Rxn-1", "Rxn-2"), attached_to_fluid_package=True
    )

    def test_member_order_does_not_matter(self):
        wanted = EnsureReactionSetArgs(name="RxnSet-1", reactions=("Rxn-2", "Rxn-1"))
        assert reaction_set_differences(self.existing, wanted) == ()

    def test_different_members_are_reported(self):
        wanted = EnsureReactionSetArgs(name="RxnSet-1", reactions=("Rxn-1",))
        assert reaction_set_differences(self.existing, wanted)

    def test_set_not_attached_to_the_fluid_package_is_reported(self):
        detached = self.existing.model_copy(update={"attached_to_fluid_package": False})
        wanted = EnsureReactionSetArgs(name="RxnSet-1", reactions=("Rxn-1", "Rxn-2"))
        assert reaction_set_differences(detached, wanted) == ("反应集没有挂到流体包",)


def stream_snapshot(**changes):
    values = {
        "name": "Feed",
        "temperature_c": 380.0,
        "pressure_bar": 25.0,
        "molar_flow_kmol_h": 108.53,
        "mass_flow_kg_h": 10000.0,
        "vapour_fraction": 1.0,
        "heavy_liquid_fraction": 0.0,
        "components": (
            StreamComponent(
                name="Toluene", mole_fraction=1.0, molar_flow_kmol_h=108.53, mass_flow_kg_h=10000.0
            ),
            StreamComponent(
                name="Benzene", mole_fraction=0.0, molar_flow_kmol_h=0.0, mass_flow_kg_h=0.0
            ),
        ),
    }
    return StreamSnapshot(**{**values, **changes})


def conditions(**changes):
    values = {
        "temperature_c": 380.0,
        "pressure_bar": 25.0,
        "composition": (CompositionEntry(component="Toluene", mole_fraction=1.0),),
        "mass_flow_kg_h": 10000.0,
    }
    return FeedConditions(**{**values, **changes})


class TestStreams:
    def test_stream_matching_its_conditions_has_no_difference(self):
        assert stream_differences(stream_snapshot(), conditions()) == ()

    def test_unlisted_components_are_expected_to_be_zero(self):
        assert stream_differences(stream_snapshot(), conditions()) == ()
        polluted = stream_snapshot(
            components=(
                StreamComponent(
                    name="Toluene", mole_fraction=0.9, molar_flow_kmol_h=None, mass_flow_kg_h=None
                ),
                StreamComponent(
                    name="Benzene", mole_fraction=0.1, molar_flow_kmol_h=None, mass_flow_kg_h=None
                ),
            )
        )
        found = stream_differences(polluted, conditions())
        assert len(found) == 2

    def test_temperature_pressure_and_flow_differences_are_reported(self):
        found = stream_differences(stream_snapshot(temperature_c=400.0), conditions())
        assert len(found) == 1
        assert "温度" in found[0]
        assert stream_differences(stream_snapshot(pressure_bar=30.0), conditions())
        assert stream_differences(stream_snapshot(mass_flow_kg_h=9000.0), conditions())

    def test_molar_flow_is_compared_when_the_condition_gives_molar_flow(self):
        wanted = conditions(mass_flow_kg_h=None, molar_flow_kmol_h=108.53)
        assert stream_differences(stream_snapshot(), wanted) == ()
        assert stream_differences(stream_snapshot(molar_flow_kmol_h=100.0), wanted)

    def test_unknown_values_count_as_different(self):
        unknown = stream_snapshot(temperature_c=None, mass_flow_kg_h=None)
        assert len(stream_differences(unknown, conditions())) == 2

    def test_floating_point_noise_from_unit_conversion_is_ignored(self):
        noisy = stream_snapshot(temperature_c=380.0000000001, pressure_bar=25.0000001)
        assert stream_differences(noisy, conditions()) == ()


def reactor_snapshot(**changes):
    values = {
        "name": "CRV-100",
        "reactor_type": ReactorType.CONVERSION,
        "feeds": ("Feed",),
        "vapour_product": "Vap",
        "liquid_product": "Liq",
        "energy_stream": None,
        "reaction_set": "RxnSet-1",
        "pressure_drop_bar": 0.0,
    }
    return ReactorSnapshot(**{**values, **changes})


def reactor_args(**changes):
    values = {
        "name": "CRV-100",
        "reactor_type": ReactorType.CONVERSION,
        "feeds": ("Feed",),
        "vapour_product": "Vap",
        "liquid_product": "Liq",
        "reaction_set": "RxnSet-1",
        "heat_mode": HeatMode.ADIABATIC,
    }
    return EnsureReactorArgs(**{**values, **changes})


class TestReactors:
    def test_matching_reactor_has_no_difference(self):
        assert reactor_differences(reactor_snapshot(), reactor_args()) == ()

    def test_feed_order_does_not_matter(self):
        existing = reactor_snapshot(feeds=("FeedA", "FeedB"))
        assert reactor_differences(existing, reactor_args(feeds=("FeedB", "FeedA"))) == ()

    def test_each_connection_difference_is_reported(self):
        for changes in (
            {"reactor_type": ReactorType.GIBBS},
            {"feeds": ("Other",)},
            {"vapour_product": "Other"},
            {"liquid_product": "Other"},
            {"reaction_set": "Other"},
            {"energy_stream": "Q-100"},
            {"pressure_drop_bar": 0.5},
        ):
            assert reactor_differences(reactor_snapshot(**changes), reactor_args()), changes

    def test_unconnected_reaction_set_is_a_difference(self):
        assert reactor_differences(reactor_snapshot(reaction_set=None), reactor_args())

    def test_energy_stream_connection_is_compared(self):
        wanted = reactor_args(
            energy_stream="Q-100", heat_mode=HeatMode.SPECIFIED_OUTLET_TEMPERATURE
        )
        assert reactor_differences(reactor_snapshot(energy_stream="Q-100"), wanted) == ()
        assert reactor_differences(reactor_snapshot(), wanted)


class TestRequireMatch:
    def test_no_difference_raises_nothing(self):
        require_match(ErrorCode.CONFLICT, "物流 Feed", ())

    def test_differences_become_a_domain_error_with_every_difference_in_the_details(self):
        with pytest.raises(ReactorAgentError) as caught:
            require_match(ErrorCode.CONFLICT, "物流 Feed", ("温度不同", "压力不同"))
        error = caught.value
        assert error.code is ErrorCode.CONFLICT
        assert "物流 Feed" in error.message
        assert "温度不同" in error.message
        assert error.details == {"differences": "温度不同；压力不同"}
