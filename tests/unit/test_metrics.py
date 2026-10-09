"""派生指标：转化率、收率、比值，以及分母为零、量读不到的情况。数值都是手算的期望值。"""

import pytest

from builders import (
    GASIFICATION_METHANATION,
    GASIFICATION_SHIFT,
    equilibrium_scenario,
    feed_flows,
    golden_data,
    spec_from,
)
from reactor_agent.spec.enums import MetricKind, MetricUnit
from reactor_agent.validation.metrics import compute_metrics

TOLERANCE = 1e-6


def metrics_of(scenario):
    return {metric.name: metric for metric in compute_metrics(scenario.context)}


def with_metrics(scenario, *requests):
    data = golden_data("smr_equilibrium")
    data["metrics"] = list(requests)
    return scenario.with_spec(spec_from(data))


class TestRequestedMetrics:
    def test_conversion_is_the_percentage_of_the_feed_that_disappeared(self, equilibrium):
        # 甲烷进 1000，出 450
        metric = metrics_of(equilibrium)["Methane 转化率"]
        assert metric.value == pytest.approx(55.0, abs=TOLERANCE)
        assert (metric.unit, metric.request.kind) == (MetricUnit.PERCENT, MetricKind.CONVERSION)

    def test_ratio_compares_two_outlet_flows(self, equilibrium):
        # 氢气 1850，CO 350
        metric = metrics_of(equilibrium)["Hydrogen/CO"]
        assert metric.value == pytest.approx(1850 / 350, abs=TOLERANCE)
        assert (metric.unit, metric.request.kind) == (MetricUnit.RATIO, MetricKind.RATIO)

    def test_yield_is_not_multiplied_by_a_stoichiometric_coefficient(self, equilibrium):
        # 出口氢气 1850 kmol/h，进口甲烷 1000 kmol/h：收率 185%，反应式里氢气的系数 3 不参与
        request = {"kind": "yield", "product": "Hydrogen", "basis": "Methane"}
        metric = metrics_of(with_metrics(equilibrium, request))["Hydrogen 收率"]
        assert metric.value == pytest.approx(185.0, abs=TOLERANCE)
        assert (metric.unit, metric.request.kind) == (MetricUnit.PERCENT, MetricKind.YIELD)

    def test_the_two_stage_model_gives_the_carbon_conversion_and_the_monoxide_yield(
        self, gasification
    ):
        feed = feed_flows(gasification.spec)
        carbon, water = feed["Carbon"], feed["H2O"]
        monoxide = water * (1 - GASIFICATION_METHANATION - GASIFICATION_SHIFT)
        found = metrics_of(gasification)
        assert found["CO 收率"].value == pytest.approx(monoxide / carbon * 100, abs=TOLERANCE)
        assert found["Carbon 转化率"].value == pytest.approx(water / carbon * 100, abs=TOLERANCE)

    def test_metrics_follow_the_order_of_the_requests(self, equilibrium):
        assert [m.name for m in compute_metrics(equilibrium.context)] == [
            "Methane 转化率",
            "Hydrogen/CO",
        ]

    def test_a_spec_without_requests_gives_no_metrics(self, equilibrium):
        assert compute_metrics(with_metrics(equilibrium).context) == ()

    def test_every_metric_carries_its_definition(self, equilibrium, gasification):
        for scenario in (equilibrium, gasification):
            for metric in compute_metrics(scenario.context):
                assert metric.name in metric.definition
                assert "÷" in metric.definition

    def test_the_definition_of_a_conversion_says_that_all_streams_are_added(self, equilibrium):
        assert "全部物流" in metrics_of(equilibrium)["Methane 转化率"].definition

    def test_the_definition_of_a_yield_says_it_has_no_stoichiometric_factor(self, equilibrium):
        request = {"kind": "yield", "product": "CO", "basis": "Methane"}
        assert (
            "不乘计量系数" in metrics_of(with_metrics(equilibrium, request))["CO 收率"].definition
        )


class TestStreamsThatAreAdded:
    def test_conversion_adds_every_outlet_including_the_solid_one(self, gasification):
        # 碳只在第一段的液相出料里：Liq-1 是 C0 - W，转化率 W / C0
        feed = feed_flows(gasification.spec)
        expected = (feed["H2O"] / feed["Carbon"]) * 100
        assert metrics_of(gasification)["Carbon 转化率"].value == pytest.approx(expected, abs=1e-6)

    def test_the_intermediate_stream_is_not_an_outlet(self, gasification):
        noisy = gasification.with_component("Vap-1", "Carbon", molar_flow_kmol_h=5000.0)
        assert metrics_of(noisy)["Carbon 转化率"].value == pytest.approx(
            metrics_of(gasification)["Carbon 转化率"].value
        )


class TestMissingValues:
    def test_ratio_with_a_zero_denominator_is_none(self, equilibrium):
        broken = equilibrium.with_component("Vap", "CO", molar_flow_kmol_h=0.0)
        assert metrics_of(broken)["Hydrogen/CO"].value is None

    def test_conversion_of_something_that_was_not_fed_is_none(self, equilibrium):
        request = {"kind": "conversion", "component": "CO2"}
        assert metrics_of(with_metrics(equilibrium, request))["CO2 转化率"].value is None

    def test_yield_on_a_basis_that_was_not_fed_is_none(self, equilibrium):
        request = {"kind": "yield", "product": "Hydrogen", "basis": "CO"}
        assert metrics_of(with_metrics(equilibrium, request))["Hydrogen 收率"].value is None

    def test_an_unreadable_flow_makes_only_the_metrics_that_use_it_none(self, equilibrium):
        broken = equilibrium.with_component("Vap", "CO", molar_flow_kmol_h=None)
        found = metrics_of(broken)
        assert found["Hydrogen/CO"].value is None
        assert found["Methane 转化率"].value == pytest.approx(55.0, abs=TOLERANCE)

    def test_a_missing_outlet_makes_every_metric_none(self, equilibrium):
        found = metrics_of(equilibrium.without_stream("Liq"))
        assert [m.value for m in found.values()] == [None, None]

    def test_a_missing_feed_makes_every_metric_none(self, equilibrium):
        found = metrics_of(equilibrium.without_stream("Feed"))
        assert [m.value for m in found.values()] == [None, None]

    def test_a_none_value_never_raises(self):
        scenario = equilibrium_scenario().without_stream("Vap")
        assert all(metric.value is None for metric in compute_metrics(scenario.context))
