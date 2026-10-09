"""ModelSpec：三份规格能加载，每条一致性规则有一个违反它的用例，哈希和假设可用。"""

import copy
import json

import pytest
from pydantic import ValidationError

from builders import GOLDEN
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import HeatMode, MetricKind, ReactorType
from reactor_agent.spec.loading import read_document
from reactor_agent.spec.model_spec import (
    ConversionMetric,
    ModelSpec,
    RatioMetric,
    YieldMetric,
    is_assumed,
    load_model_spec,
    metric_components,
    spec_hash,
)

SPECS = ("smr_equilibrium", "toluene_conversion", "slurry_gibbs")


def golden(name):
    return read_document(GOLDEN / f"{name}.yaml")


def changed(name, **changes):
    """黄金规格的字典形式，顶层字段按 changes 替换，用来造违反某条规则的规格。"""
    data = copy.deepcopy(golden(name))
    data.update(changes)
    return data


def rejected(data, match):
    with pytest.raises(ValidationError, match=match):
        ModelSpec.model_validate(data)


@pytest.mark.parametrize("name", SPECS)
def test_golden_spec_loads(name):
    spec = load_model_spec(GOLDEN / f"{name}.yaml")
    assert spec.components
    assert spec.cases


def test_golden_specs_have_the_reactor_types_of_their_scenarios():
    types = {name: load_model_spec(GOLDEN / f"{name}.yaml").reactor_type for name in SPECS}
    assert types == {
        "smr_equilibrium": ReactorType.EQUILIBRIUM,
        "toluene_conversion": ReactorType.CONVERSION,
        "slurry_gibbs": ReactorType.GIBBS,
    }


@pytest.mark.parametrize("name", SPECS)
def test_hash_survives_a_json_round_trip(name):
    spec = load_model_spec(GOLDEN / f"{name}.yaml")
    again = ModelSpec.model_validate_json(spec.model_dump_json())
    assert again == spec
    assert spec_hash(again) == spec_hash(spec)
    assert len(spec_hash(spec)) == 64


def test_hash_changes_when_any_value_changes():
    spec = load_model_spec(GOLDEN / "smr_equilibrium.yaml")
    data = spec.model_dump(mode="json")
    data["feeds"][0]["temperature_c"] += 1.0
    assert spec_hash(ModelSpec.model_validate(data)) != spec_hash(spec)


def test_hash_does_not_depend_on_the_order_keys_were_written():
    spec = load_model_spec(GOLDEN / "toluene_conversion.yaml")
    data = spec.model_dump(mode="json")
    shuffled = dict(reversed(list(data.items())))
    assert spec_hash(ModelSpec.model_validate(shuffled)) == spec_hash(spec)


class TestConsistencyRules:
    def test_repeated_component_is_rejected(self):
        data = changed("smr_equilibrium", components=["Methane", "H2O", "CO", "CO2", "CO2"])
        rejected(data, "重复")

    def test_feed_component_outside_the_component_list_is_rejected(self):
        data = changed("smr_equilibrium", components=["Methane", "CO", "CO2", "Hydrogen"])
        rejected(data, r"feeds\[0\]\.composition.*H2O")

    def test_reaction_component_outside_the_component_list_is_rejected(self):
        data = changed("smr_equilibrium", components=["Methane", "H2O", "CO", "Hydrogen"])
        rejected(data, r"reactions\[1\].*CO2")

    def test_metric_component_outside_the_component_list_is_rejected(self):
        data = changed("toluene_conversion")
        data["metrics"] = [{"kind": "conversion", "component": "Methane"}]
        rejected(data, r"metrics\[0\].*Methane")

    def test_repeated_feed_name_is_rejected(self):
        data = changed("toluene_conversion")
        data["feeds"] = [data["feeds"][0], data["feeds"][0]]
        rejected(data, "进料名")

    def test_composition_must_sum_to_one(self):
        data = changed("smr_equilibrium")
        data["feeds"][0]["composition"][0]["mole_fraction"] = 0.3
        rejected(data, "之和应为 1")

    def test_exactly_one_kind_of_flow_must_be_given(self):
        data = changed("toluene_conversion")
        data["feeds"][0]["molar_flow_kmol_h"] = 100.0
        rejected(data, "二选一")
        del data["feeds"][0]["molar_flow_kmol_h"], data["feeds"][0]["mass_flow_kg_h"]
        rejected(data, "二选一")

    @pytest.mark.parametrize(
        ("field", "value"),
        [("temperature_c", -300.0), ("pressure_bar", 0.0), ("mass_flow_kg_h", -5.0)],
    )
    def test_feed_values_must_be_physical(self, field, value):
        data = changed("toluene_conversion")
        data["feeds"][0][field] = value
        rejected(data, "feeds")

    @pytest.mark.parametrize("percent", [0.0, 100.5, -1.0])
    def test_conversion_must_be_between_zero_and_a_hundred_percent(self, percent):
        data = changed("toluene_conversion")
        data["reactions"][0]["conversion_percent"] = percent
        rejected(data, "conversion_percent")

    def test_pressure_drop_has_no_default(self):
        data = changed("toluene_conversion")
        del data["pressure_drop_bar"]
        rejected(data, "pressure_drop_bar")

    def test_negative_pressure_drop_is_rejected(self):
        rejected(changed("toluene_conversion", pressure_drop_bar=-0.1), "pressure_drop_bar")

    def test_unknown_fields_are_rejected_instead_of_ignored(self):
        rejected(changed("toluene_conversion", reactor_volume_m3=10.0), "reactor_volume_m3")

    def test_a_spec_needs_at_least_one_case_and_one_feed(self):
        rejected(changed("toluene_conversion", cases=[]), "cases")
        rejected(changed("toluene_conversion", feeds=[]), "feeds")


class TestCasesAgainstTheHeatMode:
    def test_case_names_must_be_unique(self):
        data = changed("smr_equilibrium")
        data["cases"][1]["name"] = data["cases"][0]["name"]
        rejected(data, "工况名")

    def test_outlet_temperature_mode_needs_a_temperature_in_every_case(self):
        data = changed("smr_equilibrium")
        del data["cases"][1]["outlet_temperature_c"]
        rejected(data, r"cases\[1\].*出口温度")

    def test_outlet_temperature_mode_refuses_a_duty(self):
        data = changed("smr_equilibrium")
        data["cases"][0]["duty_kw"] = 1000.0
        rejected(data, r"cases\[0\]")

    def test_adiabatic_cases_carry_no_values(self):
        data = changed("toluene_conversion")
        data["cases"][0]["outlet_temperature_c"] = 400.0
        rejected(data, "绝热")

    def test_duty_mode_needs_a_duty_and_no_temperature(self):
        data = changed("smr_equilibrium", heat_mode="specified_duty")
        rejected(data, "热负荷")
        data["cases"] = [{"name": "q", "duty_kw": 4.0e4}]
        assert ModelSpec.model_validate(data).heat_mode is HeatMode.SPECIFIED_DUTY

    def test_temperature_below_absolute_zero_is_rejected(self):
        data = changed("smr_equilibrium")
        data["cases"][0]["outlet_temperature_c"] = -300.0
        rejected(data, "cases")


class TestCaseNames:
    """工况名会用来给每个工况的 .hsc 文件命名，来自 LLM 的输出，不能带路径。"""

    @pytest.mark.parametrize("name", ["T710", "base", "工况 1", "710 °C", "case-2_a", "a.b"])
    def test_ordinary_names_are_accepted(self, name):
        data = changed("smr_equilibrium")
        data["cases"][0]["name"] = name
        assert ModelSpec.model_validate(data).cases[0].name == name

    @pytest.mark.parametrize(
        "name",
        [
            "..\\..\\evil",
            "a/b",
            "a:b",
            "a*b",
            "a?b",
            'a"b',
            "a<b",
            "a>b",
            "a|b",
            " lead",
            "trail ",
            ".hidden",
            "dot.",
            "tab\there",
        ],
    )
    def test_names_that_cannot_be_file_names_are_rejected(self, name):
        data = changed("smr_equilibrium")
        data["cases"][0]["name"] = name
        rejected(data, "工况名")


class TestAssumptions:
    def test_assumption_ids_must_be_unique(self):
        data = changed("toluene_conversion")
        data["assumptions"][1]["id"] = data["assumptions"][0]["id"]
        rejected(data, "假设编号")

    def test_assumption_must_point_at_a_field_that_exists(self):
        data = changed("toluene_conversion")
        data["assumptions"][0]["field_path"] = "feeds[3].mass_flow_kg_h"
        rejected(data, "不存在")

    def test_assumption_path_must_follow_the_fixed_syntax(self):
        data = changed("toluene_conversion")
        data["assumptions"][0]["field_path"] = "feeds.0.mass_flow_kg_h"
        rejected(data, "field_path")

    def test_assumed_field_is_recognised(self):
        spec = load_model_spec(GOLDEN / "toluene_conversion.yaml")
        assert is_assumed(spec, "pressure_drop_bar")
        assert is_assumed(spec, "feeds[0].pressure_bar")
        assert is_assumed(spec, "heat_mode")

    def test_field_inside_an_assumed_field_is_assumed_too(self):
        spec = load_model_spec(GOLDEN / "toluene_conversion.yaml")
        assert is_assumed(spec, "reactions[0].stoichiometry[2].coefficient")

    def test_fields_that_nobody_assumed_are_not(self):
        spec = load_model_spec(GOLDEN / "toluene_conversion.yaml")
        assert not is_assumed(spec, "feeds[0].temperature_c")
        assert not is_assumed(spec, "reactions[0].base_component")

    def test_a_sibling_with_a_similar_name_is_not_covered(self):
        spec = load_model_spec(GOLDEN / "toluene_conversion.yaml")
        assert not is_assumed(spec, "pressure_drop_bar_extra")
        assert not is_assumed(spec, "feeds[10].pressure_bar")


class TestMetricRequests:
    def test_requests_are_told_apart_by_kind(self):
        spec = load_model_spec(GOLDEN / "slurry_gibbs.yaml")
        assert isinstance(spec.metrics[0], YieldMetric)
        assert isinstance(spec.metrics[1], ConversionMetric)
        smr = load_model_spec(GOLDEN / "smr_equilibrium.yaml")
        assert isinstance(smr.metrics[1], RatioMetric)
        assert [m.kind for m in smr.metrics] == [MetricKind.CONVERSION, MetricKind.RATIO]

    def test_components_of_each_kind_of_request(self):
        assert metric_components(ConversionMetric(component="CO")) == ("CO",)
        assert metric_components(YieldMetric(product="CO", basis="Carbon")) == ("CO", "Carbon")
        ratio = RatioMetric(numerator="Hydrogen", denominator="CO")
        assert metric_components(ratio) == ("Hydrogen", "CO")

    def test_unknown_kind_is_rejected(self):
        data = changed("toluene_conversion")
        data["metrics"] = [{"kind": "selectivity", "component": "Toluene"}]
        rejected(data, "metrics")


class TestLoading:
    def test_missing_file_is_an_io_error(self, tmp_path):
        with pytest.raises(ReactorAgentError) as caught:
            load_model_spec(tmp_path / "nope.yaml")
        assert caught.value.code is ErrorCode.IO

    def test_broken_text_is_a_schema_error(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text("reactor_type: [unclosed", encoding="utf-8")
        with pytest.raises(ReactorAgentError) as caught:
            load_model_spec(path)
        assert caught.value.code is ErrorCode.SCHEMA

    def test_a_file_that_is_not_utf8_is_a_schema_error_and_not_a_retryable_io_error(self, tmp_path):
        path = tmp_path / "gbk.yaml"
        path.write_bytes("reactor_type: 平衡\n".encode("gbk"))
        with pytest.raises(ReactorAgentError) as caught:
            load_model_spec(path)
        assert caught.value.code is ErrorCode.SCHEMA
        assert "UTF-8" in caught.value.message
        assert not caught.value.retryable

    def test_an_empty_file_is_a_schema_error(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        with pytest.raises(ReactorAgentError) as caught:
            load_model_spec(path)
        assert caught.value.code is ErrorCode.SCHEMA

    def test_error_message_points_at_the_wrong_field(self, tmp_path):
        data = copy.deepcopy(golden("toluene_conversion"))
        data["feeds"][0]["temperature_c"] = -300.0
        path = tmp_path / "spec.yaml"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ReactorAgentError) as caught:
            load_model_spec(path)
        assert caught.value.code is ErrorCode.SCHEMA
        assert "feeds[0].temperature_c" in caught.value.message
        assert "feeds[0].temperature_c" in caught.value.details
        assert not caught.value.retryable

    def test_json_and_yaml_give_the_same_spec(self, tmp_path):
        yaml_spec = load_model_spec(GOLDEN / "slurry_gibbs.yaml")
        path = tmp_path / "spec.json"
        path.write_text(yaml_spec.model_dump_json(), encoding="utf-8")
        assert load_model_spec(path) == yaml_spec
