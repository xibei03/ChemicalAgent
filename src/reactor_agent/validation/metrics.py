"""派生指标：按规格里的指标请求，从快照计算。

三种指标：转化率、收率、比值。定义写进结果里，报告会把它展示给用户。分母为零或者用到的量读不到
时，指标的值是 None，不参与算术，也不抛异常。进料和出料都按计划里的全部系统物流合计。
"""

from collections.abc import Sequence

from reactor_agent.spec.balances import (
    PERCENT,
    conversion_percent,
    flow_ratio,
    total_component_flow_kmol_h,
)
from reactor_agent.spec.enums import MetricUnit
from reactor_agent.spec.model_spec import ConversionMetric, MetricRequest, YieldMetric
from reactor_agent.spec.plan import system_feed_names, system_outlet_names
from reactor_agent.spec.results import CheckContext, MetricResult
from reactor_agent.spec.snapshot import StreamSnapshot


def _name_and_definition(request: MetricRequest) -> tuple[str, str, MetricUnit]:
    """指标的名字、定义和单位。"""
    if isinstance(request, ConversionMetric):
        name = f"{request.component} 转化率"
        definition = f"{name} = （进料量 − 出料量）÷ 进料量，进料和出料都按全部物流合计"
        return name, definition, MetricUnit.PERCENT
    if isinstance(request, YieldMetric):
        name = f"{request.product} 收率（以 {request.basis} 计）"
        definition = (
            f"{name} = 出料中 {request.product} 的摩尔流量 ÷ 进料中 {request.basis} 的摩尔流量"
            "（不乘计量系数）"
        )
        return name, definition, MetricUnit.PERCENT
    name = f"{request.numerator}/{request.denominator}"
    definition = (
        f"{name} = 出料中 {request.numerator} 的摩尔流量 ÷ 出料中 {request.denominator} 的摩尔流量"
    )
    return name, definition, MetricUnit.RATIO


def _value(
    request: MetricRequest, feeds: Sequence[StreamSnapshot], outlets: Sequence[StreamSnapshot]
) -> float | None:
    if isinstance(request, ConversionMetric):
        return conversion_percent(feeds, outlets, request.component)
    if isinstance(request, YieldMetric):
        made = total_component_flow_kmol_h(outlets, request.product)
        return flow_ratio(made, total_component_flow_kmol_h(feeds, request.basis), PERCENT)
    numerator = total_component_flow_kmol_h(outlets, request.numerator)
    return flow_ratio(numerator, total_component_flow_kmol_h(outlets, request.denominator))


def compute_metrics(context: CheckContext) -> tuple[MetricResult, ...]:
    """规格里每项指标请求的值，顺序与请求一致。物流缺失时所有指标都是 None。"""
    snapshot, plan = context.snapshot, context.plan
    feeds = snapshot.streams_named(system_feed_names(plan))
    outlets = snapshot.streams_named(system_outlet_names(plan))
    results = []
    for request in context.spec.metrics:
        name, definition, unit = _name_and_definition(request)
        value = None if feeds is None or outlets is None else _value(request, feeds, outlets)
        results.append(
            MetricResult(request=request, name=name, definition=definition, value=value, unit=unit)
        )
    return tuple(results)
