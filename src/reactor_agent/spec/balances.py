"""按组分、按元素合计若干股物流的量。

指标和 Recipe 的专有检查共用这些纯函数。读不到的量（None）、物流里没有这个组分，都让结果成为
None：缺值不能当作 0 参与算术，否则缺失会被悄悄算成“守恒”或“转化”。
"""

import math
from collections.abc import Iterable, Mapping, Sequence

from reactor_agent.spec.snapshot import StreamSnapshot

PERCENT = 100.0
# 小于它的摩尔流量当作没有：不能当分母，物流也算没有流量。
ZERO_FLOW_KMOL_H = 1e-9


def sum_or_none(values: Iterable[float | None]) -> float | None:
    """若干个量的合计；有一个读不到（None）就是 None，不当作 0。"""
    known = list(values)
    if any(value is None for value in known):
        return None
    return math.fsum(value for value in known if value is not None)


def component_flow_kmol_h(stream: StreamSnapshot, component: str) -> float | None:
    """一股物流里某组分的摩尔流量；物流里没有这个组分也是 None。"""
    for item in stream.components:
        if item.name == component:
            return item.molar_flow_kmol_h
    return None


def total_component_flow_kmol_h(streams: Sequence[StreamSnapshot], component: str) -> float | None:
    """若干股物流里某组分的摩尔流量合计；任何一股读不到就是 None。"""
    return sum_or_none(component_flow_kmol_h(stream, component) for stream in streams)


def total_mass_flow_kg_h(streams: Sequence[StreamSnapshot]) -> float | None:
    """若干股物流的质量流量合计；任何一股读不到就是 None。"""
    return sum_or_none(stream.mass_flow_kg_h for stream in streams)


def total_element_flow_kmol_h(
    streams: Sequence[StreamSnapshot], element: str, atoms: Mapping[str, Mapping[str, int]]
) -> float | None:
    """若干股物流里某元素的原子流量合计（kmol/h）；有组分读不到或不在 atoms 里就是 None。"""
    flows: list[float | None] = []
    for stream in streams:
        for item in stream.components:
            counts = atoms.get(item.name)
            if counts is None:
                return None
            flow = item.molar_flow_kmol_h
            flows.append(None if flow is None else flow * counts.get(element, 0))
    return sum_or_none(flows)


def flow_ratio(
    numerator: float | None, denominator: float | None, scale: float = 1.0
) -> float | None:
    """两个流量的比再乘 scale；有一个读不到或者分母为零，就是 None，不做除法。"""
    if numerator is None or denominator is None or denominator <= ZERO_FLOW_KMOL_H:
        return None
    return numerator / denominator * scale


def conversion_percent(
    feeds: Sequence[StreamSnapshot], outlets: Sequence[StreamSnapshot], component: str
) -> float | None:
    """某组分的转化率（%）：（进料量 − 出料量）÷ 进料量，进料和出料各按全部物流合计。"""
    fed = total_component_flow_kmol_h(feeds, component)
    left = total_component_flow_kmol_h(outlets, component)
    return None if fed is None or left is None else flow_ratio(fed - left, fed, PERCENT)
