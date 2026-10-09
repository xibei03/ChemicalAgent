"""V5 输出存在、V6 物理有效（计划 §12.3）：只看物料流本身的量。

V6 除了分率非负、和为 1、流量非负，还要求一股物流里的数彼此一致：各组分的流量之和等于总流量，
组分的质量流量等于摩尔流量乘分子量，摩尔分率等于组分流量占总流量的比。报告会同时展示总量和各组分
的量，它们对不上就说明读回或者求解有问题，不能让这样的数据进入结果。
"""

import math
from collections.abc import Mapping

from reactor_agent.spec.balances import ZERO_FLOW_KMOL_H, sum_or_none
from reactor_agent.spec.components import molecular_weights
from reactor_agent.spec.enums import CheckId
from reactor_agent.spec.plan import energy_stream_names, material_stream_names, system_outlet_names
from reactor_agent.spec.results import CheckContext, CheckResult, check_result
from reactor_agent.spec.snapshot import StreamSnapshot

# 摩尔分率之和与 1 的最大偏差，摩尔分率与组分流量占总流量之比的最大偏差。
FRACTION_TOLERANCE = 1e-6
# 数值噪声允许的负值下限，也是比较流量时的绝对容差。
NEGATIVE_TOLERANCE = 1e-9
# 各组分流量之和与总流量的相对偏差上限，只允许浮点误差。
SUM_TOLERANCE = 1e-6
# 组分质量流量与摩尔流量乘分子量的相对偏差上限。仿真软件的分子量和组分表里的只差在第四位有效数字。
MOLECULAR_WEIGHT_TOLERANCE = 1e-3


def _has_flow(stream: StreamSnapshot) -> bool:
    """物流有流量。流量读不到时也当作有，让后面的检查照常报告缺值。"""
    flow = stream.molar_flow_kmol_h
    return flow is None or flow > ZERO_FLOW_KMOL_H


def _missing_values(stream: StreamSnapshot) -> list[str]:
    """物流里读不到的量。没有流量的物流只要求温度、压力和流量有值，组成没有意义。"""
    state = [
        ("温度", stream.temperature_c),
        ("压力", stream.pressure_bar),
        ("摩尔流量", stream.molar_flow_kmol_h),
        ("质量流量", stream.mass_flow_kg_h),
    ]
    missing = [what for what, value in state if value is None]
    if not _has_flow(stream):
        return missing
    for item in stream.components:
        values = (item.mole_fraction, item.molar_flow_kmol_h, item.mass_flow_kg_h)
        if any(value is None for value in values):
            missing.append(f"组分 {item.name} 的组成")
    return missing


def check_outputs(context: CheckContext) -> CheckResult:
    """V5：每股出料的温度、压力、总流量有值；有流量的出料，各组分的组成也有值；能流的热负荷有值。"""
    snapshot = context.snapshot
    problems: list[str] = []
    for name in system_outlet_names(context.plan):
        stream = snapshot.stream(name)
        if stream is None:
            problems.append(f"出料 {name} 不存在")
            continue
        problems += [f"出料 {name} 的{what}没有值" for what in _missing_values(stream)]
    planned = set(energy_stream_names(context.plan))
    problems += [
        f"能流 {item.name} 的热负荷没有值"
        for item in snapshot.energy_streams
        if item.name in planned and item.duty_kw is None
    ]
    found = f"{len(system_outlet_names(context.plan))} 股出料的量都有值"
    return check_result(CheckId.OUTPUTS, "出料的温度、压力、流量和组成都有值", found, problems)


def _negative_problems(stream: StreamSnapshot) -> list[str]:
    flows = [("摩尔流量", stream.molar_flow_kmol_h), ("质量流量", stream.mass_flow_kg_h)]
    for item in stream.components:
        flows += [
            (f"{item.name} 的摩尔流量", item.molar_flow_kmol_h),
            (f"{item.name} 的质量流量", item.mass_flow_kg_h),
        ]
    problems = [
        f"{stream.name} 的{what}是负数 {value:.6g}"
        for what, value in flows
        if value is not None and value < -NEGATIVE_TOLERANCE
    ]
    fractions = [item.mole_fraction for item in stream.components]
    if any(f is not None and f < -NEGATIVE_TOLERANCE for f in fractions):
        problems.append(f"{stream.name} 有负的摩尔分率")
    return problems


def _fraction_sum_problems(stream: StreamSnapshot) -> list[str]:
    """有流量的物流，摩尔分率之和为 1。有分率读不到时归 V5。"""
    fractions = [item.mole_fraction for item in stream.components]
    known = [f for f in fractions if f is not None]
    total = math.fsum(known)
    if not _has_flow(stream) or len(known) < len(fractions):
        return []
    if math.isclose(total, 1.0, abs_tol=FRACTION_TOLERANCE):
        return []
    return [f"{stream.name} 的摩尔分率之和是 {total:.9f}，应为 1"]


def _sum_mismatch(name: str, what: str, added: float | None, total: float | None) -> list[str]:
    if added is None or total is None:
        return []
    if math.isclose(added, total, rel_tol=SUM_TOLERANCE, abs_tol=NEGATIVE_TOLERANCE):
        return []
    return [f"{name} 的各组分{what}之和是 {added:.6g}，总{what}是 {total:.6g}"]


def _total_problems(stream: StreamSnapshot) -> list[str]:
    """各组分的流量之和等于物流的总流量，摩尔和质量各一次；没有流量的物流也一样。"""
    molar = sum_or_none(item.molar_flow_kmol_h for item in stream.components)
    mass = sum_or_none(item.mass_flow_kg_h for item in stream.components)
    return [
        *_sum_mismatch(stream.name, "摩尔流量", molar, stream.molar_flow_kmol_h),
        *_sum_mismatch(stream.name, "质量流量", mass, stream.mass_flow_kg_h),
    ]


def _weight_problems(stream: StreamSnapshot, weights: Mapping[str, float]) -> list[str]:
    """组分的质量流量等于摩尔流量乘分子量。不在组分表里的组分由通用规则报告，这里跳过。"""
    problems = []
    for item in stream.components:
        weight = weights.get(item.name)
        if weight is None or item.molar_flow_kmol_h is None or item.mass_flow_kg_h is None:
            continue
        expected = item.molar_flow_kmol_h * weight
        close = math.isclose(
            item.mass_flow_kg_h,
            expected,
            rel_tol=MOLECULAR_WEIGHT_TOLERANCE,
            abs_tol=NEGATIVE_TOLERANCE,
        )
        if not close:
            problems.append(
                f"{stream.name} 的 {item.name} 质量流量是 {item.mass_flow_kg_h:.6g}，"
                f"摩尔流量乘分子量得 {expected:.6g}"
            )
    return problems


def _share_problems(stream: StreamSnapshot) -> list[str]:
    """摩尔分率等于组分的摩尔流量占总流量的比。没有流量的物流没有这个比，不检查。"""
    total = stream.molar_flow_kmol_h
    if total is None or total <= ZERO_FLOW_KMOL_H:
        return []
    return [
        f"{stream.name} 的 {item.name} 摩尔分率是 {item.mole_fraction:.6g}，"
        f"流量占比是 {item.molar_flow_kmol_h / total:.6g}"
        for item in stream.components
        if item.mole_fraction is not None
        and item.molar_flow_kmol_h is not None
        and not math.isclose(
            item.mole_fraction, item.molar_flow_kmol_h / total, abs_tol=FRACTION_TOLERANCE
        )
    ]


def _physical_problems(stream: StreamSnapshot, weights: Mapping[str, float]) -> list[str]:
    return [
        *_negative_problems(stream),
        *_fraction_sum_problems(stream),
        *_total_problems(stream),
        *_weight_problems(stream, weights),
        *_share_problems(stream),
    ]


def check_physical(context: CheckContext) -> CheckResult:
    """V6：分率非负且和为 1、流量非负、物流内部的数彼此一致。只看存在的物流，缺失的归 V2。"""
    weights = molecular_weights(context.components)
    problems: list[str] = []
    for name in material_stream_names(context.plan):
        stream = context.snapshot.stream(name)
        if stream is not None:
            problems += _physical_problems(stream, weights)
    expected = (
        f"摩尔分率非负且和为 1（±{FRACTION_TOLERANCE:.0e}），流量非负；各组分之和等于总量，"
        "组分质量流量等于摩尔流量乘分子量，摩尔分率等于流量占比"
    )
    return check_result(CheckId.PHYSICAL, expected, "全部有效", problems)
