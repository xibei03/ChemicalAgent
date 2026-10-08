"""入参模型拒绝非法值：负的流量、和不为 1 的组成、同时给了两种流量、白名单之外的变量等。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from reactor_agent.spec.enums import (
    HeatMode,
    KeqSource,
    ReactionKind,
    ReactionPhase,
    ReactorType,
    SpecVariable,
    StreamKind,
    ToolName,
)
from reactor_agent.spec.tool_args import (
    CloseCaseArgs,
    CompositionEntry,
    ConnectArgs,
    ConversionReaction,
    EnsureCaseArgs,
    EnsureReactionArgs,
    EnsureReactionSetArgs,
    EnsureReactorArgs,
    EnsureStreamArgs,
    EnsureThermoArgs,
    EquilibriumReaction,
    FeedConditions,
    ReadSnapshotArgs,
    SaveCaseArgs,
    SetSpecArgs,
    SolveArgs,
    StoichiometricTerm,
)

TOLUENE_DISPROPORTIONATION = (
    StoichiometricTerm(component="Toluene", coefficient=-2.0),
    StoichiometricTerm(component="Benzene", coefficient=1.0),
    StoichiometricTerm(component="p-Xylene", coefficient=0.24),
    StoichiometricTerm(component="m-Xylene", coefficient=0.52),
    StoichiometricTerm(component="o-Xylene", coefficient=0.24),
)
STEAM_REFORMING = (
    StoichiometricTerm(component="Methane", coefficient=-1.0),
    StoichiometricTerm(component="H2O", coefficient=-1.0),
    StoichiometricTerm(component="CO", coefficient=1.0),
    StoichiometricTerm(component="Hydrogen", coefficient=3.0),
)
CASE_PATH = Path("C:/runs/demo/model.hsc")


def feed(**changes):
    values = {
        "temperature_c": 380.0,
        "pressure_bar": 25.0,
        "composition": (CompositionEntry(component="Toluene", mole_fraction=1.0),),
        "mass_flow_kg_h": 10000.0,
    }
    return FeedConditions(**{**values, **changes})


def reactor(**changes):
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


def test_there_are_twelve_tools_and_five_reactor_types():
    assert len(ToolName) == 12
    assert {t.value for t in ReactorType} == {"conversion", "equilibrium", "gibbs", "pfr", "cstr"}


def test_models_are_frozen_and_reject_unknown_fields():
    args = CloseCaseArgs(save=True)
    with pytest.raises(ValidationError):
        args.save = False
    with pytest.raises(ValidationError):
        CloseCaseArgs(save=True, force=True)


def test_empty_argument_models_are_constructible():
    assert ConnectArgs().visible is True
    assert SaveCaseArgs().path is None
    assert ReadSnapshotArgs() == ReadSnapshotArgs()


class TestReactions:
    def test_conversion_reaction_with_fractional_coefficients_is_valid(self):
        reaction = ConversionReaction(
            stoichiometry=TOLUENE_DISPROPORTIONATION,
            base_component="Toluene",
            conversion_percent=50,
        )
        assert reaction.phase is ReactionPhase.VAPOUR
        assert reaction.kind is ReactionKind.CONVERSION

    @pytest.mark.parametrize("percent", [0.0, -5.0, 100.1, float("nan"), float("inf")])
    def test_conversion_outside_zero_to_hundred_percent_is_rejected(self, percent):
        with pytest.raises(ValidationError):
            ConversionReaction(
                stoichiometry=TOLUENE_DISPROPORTIONATION,
                base_component="Toluene",
                conversion_percent=percent,
            )

    def test_base_component_must_be_a_reactant(self):
        with pytest.raises(ValidationError, match="基准组分"):
            ConversionReaction(
                stoichiometry=TOLUENE_DISPROPORTIONATION,
                base_component="Benzene",
                conversion_percent=50,
            )

    def test_zero_coefficient_is_rejected(self):
        with pytest.raises(ValidationError, match="不能为零"):
            StoichiometricTerm(component="CO", coefficient=0.0)

    def test_reaction_needs_reactants_and_products(self):
        only_reactants = tuple(
            StoichiometricTerm(component=name, coefficient=-1.0) for name in ("CO", "H2O")
        )
        with pytest.raises(ValidationError, match="产物"):
            EquilibriumReaction(stoichiometry=only_reactants)

    def test_repeated_component_in_a_reaction_is_rejected(self):
        twice = (*STEAM_REFORMING, StoichiometricTerm(component="CO", coefficient=1.0))
        with pytest.raises(ValidationError, match="重复"):
            EquilibriumReaction(stoichiometry=twice)

    def test_fixed_k_requires_a_constant(self):
        with pytest.raises(ValidationError, match="固定 K"):
            EquilibriumReaction(stoichiometry=STEAM_REFORMING, keq_source=KeqSource.FIXED_K)

    def test_gibbs_source_must_not_carry_a_constant(self):
        with pytest.raises(ValidationError, match="固定 K"):
            EquilibriumReaction(stoichiometry=STEAM_REFORMING, equilibrium_constant=12.5)

    def test_fixed_k_with_constant_is_valid(self):
        reaction = EquilibriumReaction(
            stoichiometry=STEAM_REFORMING, keq_source=KeqSource.FIXED_K, equilibrium_constant=12.5
        )
        assert reaction.equilibrium_constant == 12.5

    def test_reaction_definition_union_is_chosen_by_kind(self):
        args = EnsureReactionArgs.model_validate(
            {
                "name": "Rxn-1",
                "reaction": {
                    "kind": "equilibrium",
                    "stoichiometry": [
                        {"component": "CO", "coefficient": -1},
                        {"component": "CO2", "coefficient": 1},
                    ],
                },
            }
        )
        assert isinstance(args.reaction, EquilibriumReaction)

    def test_unknown_reaction_kind_is_rejected(self):
        with pytest.raises(ValidationError):
            EnsureReactionArgs.model_validate({"name": "Rxn-1", "reaction": {"kind": "kinetic"}})


class TestStreams:
    def test_valid_feed_with_mass_flow(self):
        assert feed().mass_flow_kg_h == 10000.0

    @pytest.mark.parametrize("field", ["mass_flow_kg_h", "molar_flow_kmol_h", "pressure_bar"])
    @pytest.mark.parametrize("value", [-1.0, 0.0])
    def test_non_positive_flow_or_pressure_is_rejected(self, field, value):
        with pytest.raises(ValidationError):
            feed(**{field: value})

    def test_both_flows_are_rejected(self):
        with pytest.raises(ValidationError, match="二选一"):
            feed(molar_flow_kmol_h=100.0)

    def test_no_flow_is_rejected(self):
        with pytest.raises(ValidationError, match="二选一"):
            feed(mass_flow_kg_h=None)

    def test_temperature_must_be_above_absolute_zero(self):
        with pytest.raises(ValidationError):
            feed(temperature_c=-273.15)

    @pytest.mark.parametrize("second_fraction", [0.2, 0.0])
    def test_composition_not_summing_to_one_is_rejected(self, second_fraction):
        composition = (
            CompositionEntry(component="Methane", mole_fraction=0.5),
            CompositionEntry(component="H2O", mole_fraction=second_fraction),
        )
        with pytest.raises(ValidationError, match="之和应为 1"):
            feed(composition=composition)

    def test_composition_rounding_noise_is_accepted(self):
        composition = (
            CompositionEntry(component="Methane", mole_fraction=0.2703),
            CompositionEntry(component="H2O", mole_fraction=0.7297 + 1e-9),
        )
        assert feed(composition=composition).composition == composition

    def test_repeated_component_in_composition_is_rejected(self):
        composition = (
            CompositionEntry(component="Methane", mole_fraction=0.5),
            CompositionEntry(component="Methane", mole_fraction=0.5),
        )
        with pytest.raises(ValidationError, match="重复"):
            feed(composition=composition)

    def test_fraction_above_one_is_rejected(self):
        with pytest.raises(ValidationError):
            CompositionEntry(component="Methane", mole_fraction=1.5)

    def test_energy_stream_cannot_carry_conditions(self):
        with pytest.raises(ValidationError, match="能流"):
            EnsureStreamArgs(name="Q-100", kind=StreamKind.ENERGY, conditions=feed())

    def test_stream_name_with_illegal_characters_is_rejected(self):
        with pytest.raises(ValidationError):
            EnsureStreamArgs(name='Feed"; drop')


class TestReactors:
    def test_adiabatic_reactor_has_no_energy_stream(self):
        assert reactor().energy_stream is None

    def test_adiabatic_reactor_with_an_energy_stream_is_rejected(self):
        with pytest.raises(ValidationError, match="绝热"):
            reactor(energy_stream="Q-100")

    @pytest.mark.parametrize(
        "mode", [HeatMode.SPECIFIED_OUTLET_TEMPERATURE, HeatMode.SPECIFIED_DUTY]
    )
    def test_heated_reactor_needs_an_energy_stream(self, mode):
        with pytest.raises(ValidationError, match="绝热"):
            reactor(heat_mode=mode)

    def test_reactor_with_several_feeds_is_valid(self):
        assert reactor(feeds=("FeedA", "FeedB")).feeds == ("FeedA", "FeedB")

    def test_reactor_without_feeds_is_rejected(self):
        with pytest.raises(ValidationError):
            reactor(feeds=())

    def test_a_stream_cannot_be_both_feed_and_product(self):
        with pytest.raises(ValidationError, match="重复"):
            reactor(vapour_product="Feed")

    def test_negative_pressure_drop_is_rejected(self):
        with pytest.raises(ValidationError):
            reactor(pressure_drop_bar=-0.1)


class TestOtherTools:
    def test_set_spec_accepts_only_whitelisted_variables(self):
        assert SetSpecArgs(object_name="ERV-100", variable="outlet_temperature_c", value=710.0)
        with pytest.raises(ValidationError):
            SetSpecArgs(object_name="ERV-100", variable="pressure_bar", value=10.0)

    def test_set_spec_rejects_outlet_temperature_below_absolute_zero(self):
        with pytest.raises(ValidationError, match="绝对零度"):
            SetSpecArgs(
                object_name="ERV-100", variable=SpecVariable.OUTLET_TEMPERATURE_C, value=-300.0
            )

    def test_set_spec_rejects_non_finite_values(self):
        with pytest.raises(ValidationError):
            SetSpecArgs(object_name="ERV-100", variable=SpecVariable.DUTY_KW, value=float("nan"))

    def test_duty_may_be_negative(self):
        args = SetSpecArgs(object_name="ERV-100", variable=SpecVariable.DUTY_KW, value=-5000.0)
        assert args.value == -5000.0

    @pytest.mark.parametrize("timeout", [0.0, -1.0, 601.0])
    def test_solve_timeout_must_be_positive_and_bounded(self, timeout):
        with pytest.raises(ValidationError):
            SolveArgs(timeout_s=timeout)

    def test_case_path_must_be_absolute_and_end_with_hsc(self):
        assert EnsureCaseArgs(path=CASE_PATH).path == CASE_PATH
        with pytest.raises(ValidationError, match="绝对路径"):
            EnsureCaseArgs(path=Path("model.hsc"))
        with pytest.raises(ValidationError, match="扩展名"):
            EnsureCaseArgs(path=Path("C:/runs/model.txt"))
        with pytest.raises(ValidationError, match="扩展名"):
            SaveCaseArgs(path=Path("C:/runs/model.txt"))

    def test_thermo_components_must_be_unique_and_non_empty(self):
        with pytest.raises(ValidationError):
            EnsureThermoArgs(components=(), property_package="peng_robinson")
        with pytest.raises(ValidationError, match="重复"):
            EnsureThermoArgs(components=("CO", "CO"), property_package="peng_robinson")

    def test_unsupported_property_package_is_rejected(self):
        with pytest.raises(ValidationError):
            EnsureThermoArgs(components=("CO",), property_package="soave_redlich_kwong")

    def test_reaction_set_members_must_be_unique(self):
        with pytest.raises(ValidationError, match="重复"):
            EnsureReactionSetArgs(name="RxnSet-1", reactions=("Rxn-1", "Rxn-1"))
