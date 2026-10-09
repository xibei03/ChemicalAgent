"""验证层在真实 HYSYS 快照上的表现（D19，台账 L36）。

1B 的检查在手算的快照上写成，这里用 Recipe 编译三份黄金规格、通过 ToolExecutor 在 HYSYS 里执行，
把真实快照交给验证层：不能有误报，指标和参照值一致，空相出料的读回约定要成立。
"""

import math
from datetime import UTC, datetime

import pytest
from plan_runner import compile_plan, run_cases
from references import REFERENCES, SPEC_NAMES, YIELD_RANGE_PERCENT

from builders import GOLDEN, TABLE_FILE
from reactor_agent.recipes import recipe_for
from reactor_agent.spec.components import load_component_table, molecular_weights
from reactor_agent.spec.enums import MetricKind, TaskStatus
from reactor_agent.spec.model_spec import load_model_spec, spec_hash
from reactor_agent.spec.results import CaseRecord, CheckContext, Provenance
from reactor_agent.validation.checks import run_common_checks
from reactor_agent.validation.normalized import assemble_result, decide_outcome
from reactor_agent.validation.streams import MOLECULAR_WEIGHT_TOLERANCE

pytestmark = pytest.mark.hysys

EMPTY_FLOW_KMOL_H = 1e-9


def evaluate(executor, name):
    """执行一份规格的计划，返回规格、计划和每个工况的归一化结果。"""
    table = load_component_table(TABLE_FILE)
    spec = load_model_spec(GOLDEN / f"{name}.yaml")
    plan = compile_plan(spec, table)
    recipe = recipe_for(spec.reactor_type)
    results = []
    for case, snapshot in run_cases(executor, spec, plan):
        context = CheckContext(spec=spec, case=case, plan=plan, components=table, snapshot=snapshot)
        checks = (*run_common_checks(context), *recipe.checks(context))
        provenance = Provenance(
            simulator_version="HYSYS",
            case_path=snapshot.case_path,
            read_at=datetime.now(UTC),
            spec_hash=spec_hash(spec),
        )
        results.append((context, assemble_result(context, checks, provenance)))
    return spec, results


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_every_check_passes_on_the_real_snapshots_and_the_task_is_complete(
    executor, fresh_case, name
):
    spec, results = evaluate(executor, name)
    for _, result in results:
        failed = [(c.check_id.value, c.actual) for c in result.checks if not c.passed]
        assert not failed, (name, result.case_name, failed)
    records = [
        CaseRecord(case_name=r.case_name, result=r, case_file_saved=True) for _, r in results
    ]
    assert decide_outcome([case.name for case in spec.cases], records) is TaskStatus.COMPLETE


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_real_results_agree_with_the_reference_values_of_the_plan(executor, fresh_case, name):
    _, results = evaluate(executor, name)
    for _, result in results:
        stream_name, fractions, tolerance = REFERENCES[name][result.case_name]
        outlet = next(s for s in result.outlets if s.name == stream_name)
        for component in outlet.components:
            if component.name in fractions:
                assert component.mole_fraction == pytest.approx(
                    fractions[component.name], abs=tolerance
                ), (name, result.case_name, component.name)
    if name in YIELD_RANGE_PERCENT:
        low, high = YIELD_RANGE_PERCENT[name]
        yields = [
            m.value for _, r in results for m in r.metrics if m.request.kind is MetricKind.YIELD
        ]
        assert yields and all(low <= value <= high for value in yields), yields


def test_an_empty_outlet_reads_back_as_known_zero_flows_with_a_state(executor, fresh_case):
    """空相出料：温度、压力有值，总流量和各组分流量是 0.0（不是 None），分率是有值的一组数。"""
    _, results = evaluate(executor, "toluene_conversion")
    (context, _) = results[0]
    liquid = context.snapshot.stream("Liq")
    assert liquid.temperature_c is not None
    assert liquid.pressure_bar is not None
    assert liquid.molar_flow_kmol_h == 0.0
    assert liquid.mass_flow_kg_h == 0.0
    assert all(c.molar_flow_kmol_h == 0.0 for c in liquid.components)
    assert all(c.mass_flow_kg_h == 0.0 for c in liquid.components)
    assert all(c.mole_fraction is not None for c in liquid.components)


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_real_streams_are_consistent_well_inside_the_v6_tolerances(executor, fresh_case, name):
    """V6 的分子量容差（1e-3）对真实数据有足够的余量：最大偏差不到容差的十分之一。"""
    table = load_component_table(TABLE_FILE)
    weights = molecular_weights(table)
    _, results = evaluate(executor, name)
    for context, _ in results:
        for stream in context.snapshot.streams:
            for item in stream.components:
                if item.molar_flow_kmol_h and item.molar_flow_kmol_h > EMPTY_FLOW_KMOL_H:
                    expected = item.molar_flow_kmol_h * weights[item.name]
                    deviation = abs(item.mass_flow_kg_h / expected - 1.0)
                    assert deviation < MOLECULAR_WEIGHT_TOLERANCE / 10, (stream.name, item.name)
            total = math.fsum(c.molar_flow_kmol_h for c in stream.components)
            assert total == pytest.approx(stream.molar_flow_kmol_h, abs=1e-9), stream.name
