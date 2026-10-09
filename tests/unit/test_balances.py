"""按组分、按元素合计物流的量：缺值是 None，不当作 0 参与算术。"""

import pytest

from builders import component_table, golden_spec, stream_snapshot
from reactor_agent.spec.balances import (
    component_flow_kmol_h,
    conversion_percent,
    flow_ratio,
    sum_or_none,
    total_component_flow_kmol_h,
    total_element_flow_kmol_h,
    total_mass_flow_kg_h,
)
from reactor_agent.spec.components import atoms_by_component
from reactor_agent.spec.enums import ObjectState
from reactor_agent.spec.snapshot import ModelSnapshot, ObjectStatus, SolveStatus

SPEC = golden_spec("smr_equilibrium")
ATOMS = atoms_by_component(component_table())


def stream(name="A", **flows):
    return stream_snapshot(SPEC, name, flows, 25.0, 1.0)


def with_unknown_flow(item, component):
    components = tuple(
        c.model_copy(update={"molar_flow_kmol_h": None}) if c.name == component else c
        for c in item.components
    )
    return item.model_copy(update={"components": components})


class TestSums:
    def test_known_values_are_added(self):
        assert sum_or_none([1.0, 2.5]) == pytest.approx(3.5)

    def test_one_unknown_value_makes_the_sum_unknown(self):
        assert sum_or_none([1.0, None]) is None

    def test_no_values_add_up_to_zero(self):
        assert sum_or_none([]) == 0.0


class TestComponentFlows:
    def test_flow_of_a_component(self):
        assert component_flow_kmol_h(stream(Methane=3.0, H2O=2.0), "H2O") == pytest.approx(2.0)

    def test_component_that_is_not_in_the_stream_is_unknown(self):
        assert component_flow_kmol_h(stream(Methane=3.0), "Ethane") is None

    def test_unreadable_flow_is_unknown(self):
        assert (
            component_flow_kmol_h(with_unknown_flow(stream(Methane=3.0), "Methane"), "Methane")
            is None
        )

    def test_total_over_streams(self):
        streams = [stream("A", Methane=3.0), stream("B", Methane=1.5, CO=9.0)]
        assert total_component_flow_kmol_h(streams, "Methane") == pytest.approx(4.5)
        assert total_component_flow_kmol_h(streams, "CO") == pytest.approx(9.0)

    def test_total_is_unknown_when_one_stream_cannot_be_read(self):
        streams = [stream("A", Methane=3.0), with_unknown_flow(stream("B", Methane=1.0), "Methane")]
        assert total_component_flow_kmol_h(streams, "Methane") is None


class TestMassAndElements:
    def test_total_mass_adds_the_streams(self):
        a, b = stream("A", Methane=1.0), stream("B", H2O=2.0)
        assert total_mass_flow_kg_h([a, b]) == pytest.approx(16.043 + 2 * 18.015)

    def test_total_mass_is_unknown_when_a_stream_has_none(self):
        unknown = stream("B", H2O=2.0).model_copy(update={"mass_flow_kg_h": None})
        assert total_mass_flow_kg_h([stream("A", Methane=1.0), unknown]) is None

    def test_element_flow_counts_atoms_of_every_component(self):
        streams = [stream("A", Methane=2.0, H2O=3.0), stream("B", Hydrogen=1.0)]
        assert total_element_flow_kmol_h(streams, "C", ATOMS) == pytest.approx(2.0)
        assert total_element_flow_kmol_h(streams, "H", ATOMS) == pytest.approx(8 + 6 + 2)
        assert total_element_flow_kmol_h(streams, "O", ATOMS) == pytest.approx(3.0)

    def test_element_that_no_component_has_is_zero(self):
        assert total_element_flow_kmol_h([stream(Methane=2.0)], "S", ATOMS) == pytest.approx(0.0)

    def test_element_flow_is_unknown_when_a_flow_cannot_be_read(self):
        broken = with_unknown_flow(stream(Methane=2.0), "Methane")
        assert total_element_flow_kmol_h([broken], "C", ATOMS) is None

    def test_element_flow_is_unknown_for_a_component_without_a_formula(self):
        assert total_element_flow_kmol_h([stream(Methane=2.0)], "C", {"H2O": {"H": 2}}) is None


class TestRatiosAndConversion:
    def test_ratio_is_scaled(self):
        assert flow_ratio(1.0, 4.0) == pytest.approx(0.25)
        assert flow_ratio(1.0, 4.0, 100.0) == pytest.approx(25.0)

    @pytest.mark.parametrize(("numerator", "denominator"), [(None, 1.0), (1.0, None), (1.0, 0.0)])
    def test_ratio_with_a_missing_or_zero_denominator_is_unknown(self, numerator, denominator):
        assert flow_ratio(numerator, denominator) is None

    def test_conversion_is_the_fraction_that_disappeared(self):
        feeds = [stream("F", Methane=10.0)]
        outlets = [stream("V", Methane=4.0), stream("L", Methane=1.0)]
        assert conversion_percent(feeds, outlets, "Methane") == pytest.approx(50.0)

    def test_a_component_that_is_produced_has_a_negative_conversion(self):
        assert conversion_percent([stream(Methane=1.0, CO=2.0)], [stream(CO=3.0)], "CO") == (
            pytest.approx(-50.0)
        )

    def test_conversion_of_something_that_was_not_fed_is_unknown(self):
        assert conversion_percent([stream(Methane=1.0)], [stream(CO=3.0)], "CO") is None

    def test_conversion_is_unknown_when_the_outlet_cannot_be_read(self):
        outlet = with_unknown_flow(stream(Methane=1.0), "Methane")
        assert conversion_percent([stream(Methane=2.0)], [outlet], "Methane") is None


class TestSnapshotLookups:
    def snapshot(self):
        return ModelSnapshot(
            case_path="case.hsc",
            thermo=None,
            reactions=(),
            reaction_sets=(),
            streams=(stream("A", Methane=1.0), stream("B", H2O=1.0)),
            energy_streams=(),
            reactors=(),
            solve=SolveStatus(
                is_solving=False,
                objects=(
                    ObjectStatus(name="A", type_name="stream", state=ObjectState.OK),
                    ObjectStatus(name="R", type_name="reactor", state=ObjectState.NOT_SOLVED),
                    ObjectStatus(name="S", type_name="stream", state=ObjectState.WARNING),
                ),
            ),
        )

    def test_stream_is_found_by_name(self):
        assert self.snapshot().stream("B").name == "B"
        assert self.snapshot().stream("C") is None

    def test_streams_named_keeps_the_requested_order(self):
        found = self.snapshot().streams_named(["B", "A"])
        assert [s.name for s in found] == ["B", "A"]

    def test_streams_named_is_unknown_when_one_is_missing(self):
        assert self.snapshot().streams_named(["A", "C"]) is None

    def test_unsolved_objects_exclude_warnings(self):
        solve = self.snapshot().solve
        assert [o.name for o in solve.unsolved_objects] == ["R"]
        assert not solve.solved
