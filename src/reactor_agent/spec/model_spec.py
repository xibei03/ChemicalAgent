"""ModelSpec：描述“要建一个什么样的反应器模型”。

它是“代码已经接受的规格”，里面没有待换算的单位，也没有歧义：温度 °C，压力 bar（绝压），流量
kmol/h 或 kg/h，组成是摩尔分率，转化率是百分数。后面所有阶段都建立在它上面。这里的校验只管通用的
一致性；随反应器类型变化的要求在 Recipe 的规则里，需要组分表的检查（组分名、反应的元素守恒）
也在那里。
"""

import hashlib
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import HeatMode, MetricKind, PropertyPackage, ReactorType
from reactor_agent.spec.loading import parse_model, read_document
from reactor_agent.spec.tool_args import (
    ComponentName,
    ConversionReaction,
    FeedConditions,
    FiniteFloat,
    PressureDropBar,
    ReactionDefinition,
    TemperatureC,
    check_unique,
)

Label = Annotated[str, StringConstraints(min_length=1, max_length=60)]
# 字段路径的固定写法：用点分隔字段名，序列用方括号加下标，如 feeds[0].mass_flow_kg_h。
FIELD_PATH = re.compile(r"^[A-Za-z_]\w*(\[\d+\])?(\.[A-Za-z_]\w*(\[\d+\])?)*$")
PATH_PART = re.compile(r"([A-Za-z_]\w*)|\[(\d+)\]")
# 热模式 → 工况里必须有的值：(出口温度, 热负荷)。其余的值不能给，不然是过规定。
CASE_VALUES = {
    HeatMode.SPECIFIED_OUTLET_TEMPERATURE: (True, False),
    HeatMode.SPECIFIED_DUTY: (False, True),
    HeatMode.ADIABATIC: (False, False),
}
CASE_VALUE_MEANING = {
    HeatMode.SPECIFIED_OUTLET_TEMPERATURE: "每个工况都要有出口温度，不能有热负荷",
    HeatMode.SPECIFIED_DUTY: "每个工况都要有热负荷，不能有出口温度",
    HeatMode.ADIABATIC: "绝热的工况既没有出口温度也没有热负荷",
}


class FeedSpec(FeedConditions):
    """一股进料。名字只是规格里的标签，HYSYS 里的对象名由 Recipe 生成。"""

    name: Label


class OperatingCase(FrozenModel):
    """一个工况：名字，以及热模式要求的那个值（出口温度或热负荷）。"""

    name: Label
    outlet_temperature_c: TemperatureC | None = None
    duty_kw: FiniteFloat | None = None


class ConversionMetric(FrozenModel):
    """转化率：（进料量 − 出料量）÷ 进料量，进料和出料都按全部物流合计。"""

    kind: Literal[MetricKind.CONVERSION] = MetricKind.CONVERSION
    component: ComponentName


class YieldMetric(FrozenModel):
    """收率：产物的出料摩尔流量 ÷ 基准组分的进料摩尔流量，不乘计量系数。"""

    kind: Literal[MetricKind.YIELD] = MetricKind.YIELD
    product: ComponentName
    basis: ComponentName


class RatioMetric(FrozenModel):
    """比值：两个组分出料摩尔流量之比。"""

    kind: Literal[MetricKind.RATIO] = MetricKind.RATIO
    numerator: ComponentName
    denominator: ComponentName


MetricRequest = Annotated[ConversionMetric | YieldMetric | RatioMetric, Field(discriminator="kind")]


class Assumption(FrozenModel):
    """一条假设：编号、针对的字段（字段路径）、取值和理由。"""

    id: Label
    field_path: Annotated[str, StringConstraints(pattern=FIELD_PATH.pattern)]
    value: str
    reason: str


def metric_components(metric: ConversionMetric | YieldMetric | RatioMetric) -> tuple[str, ...]:
    """一个指标请求用到的组分。"""
    if isinstance(metric, ConversionMetric):
        return (metric.component,)
    if isinstance(metric, YieldMetric):
        return (metric.product, metric.basis)
    return (metric.numerator, metric.denominator)


def _resolves(data: object, path: str) -> bool:
    """字段路径在导出的数据（字典和列表）里是不是真的存在。"""
    node = data
    for name, index in PATH_PART.findall(path):
        if name and isinstance(node, dict) and name in node:
            node = node[name]
        elif index and isinstance(node, list) and int(index) < len(node):
            node = node[int(index)]
        else:
            return False
    return True


class ModelSpec(FrozenModel):
    """要建的模型：反应器类型、物性包、组分、进料、反应、压降、热模式、工况、待求指标和假设。"""

    reactor_type: ReactorType
    property_package: PropertyPackage
    components: tuple[ComponentName, ...] = Field(min_length=1)
    feeds: tuple[FeedSpec, ...] = Field(min_length=1)
    reactions: tuple[ReactionDefinition, ...] = ()
    pressure_drop_bar: PressureDropBar
    heat_mode: HeatMode
    cases: tuple[OperatingCase, ...] = Field(min_length=1)
    metrics: tuple[MetricRequest, ...] = ()
    assumptions: tuple[Assumption, ...] = ()

    def _component_references(self) -> Iterator[tuple[str, tuple[str, ...]]]:
        """规格里每处用到组分的地方：字段路径，以及用到的组分名。"""
        for index, feed in enumerate(self.feeds):
            yield f"feeds[{index}].composition", tuple(e.component for e in feed.composition)
        for index, reaction in enumerate(self.reactions):
            names = [term.component for term in reaction.stoichiometry]
            if isinstance(reaction, ConversionReaction):
                names.append(reaction.base_component)
            yield f"reactions[{index}]", tuple(names)
        for index, metric in enumerate(self.metrics):
            yield f"metrics[{index}]", metric_components(metric)

    @model_validator(mode="after")
    def _components_are_declared(self) -> Self:
        check_unique(self.components, "组分表")
        check_unique(tuple(feed.name for feed in self.feeds), "进料名")
        known = set(self.components)
        for path, names in self._component_references():
            unknown = sorted(set(names) - known)
            if unknown:
                raise ValueError(f"{path}：用到的组分 {unknown} 不在 components 里")
        return self

    @model_validator(mode="after")
    def _cases_match_the_heat_mode(self) -> Self:
        check_unique(tuple(case.name for case in self.cases), "工况名")
        for index, case in enumerate(self.cases):
            given = (case.outlet_temperature_c is not None, case.duty_kw is not None)
            if given != CASE_VALUES[self.heat_mode]:
                meaning = CASE_VALUE_MEANING[self.heat_mode]
                raise ValueError(f"cases[{index}]：热模式是 {self.heat_mode.value}，{meaning}")
        return self

    @model_validator(mode="after")
    def _assumptions_point_at_real_fields(self) -> Self:
        check_unique(tuple(item.id for item in self.assumptions), "假设编号")
        data = self.model_dump(mode="json")
        for index, item in enumerate(self.assumptions):
            if not _resolves(data, item.field_path):
                raise ValueError(f"assumptions[{index}]：字段路径 {item.field_path} 在规格里不存在")
        return self


def _covers(assumed: str, queried: str) -> bool:
    return queried == assumed or queried.startswith((assumed + ".", assumed + "["))


def is_assumed(spec: ModelSpec, field_path: str) -> bool:
    """规格里的某个字段是不是假设：假设登记在这个字段本身，或者登记在包含它的字段上。"""
    return any(_covers(item.field_path, field_path) for item in spec.assumptions)


def spec_hash(spec: ModelSpec) -> str:
    """规格的哈希：对按键排序的规范化 JSON 取 sha256。同一份规格导出再加载，哈希不变。"""
    canonical = json.dumps(
        spec.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_model_spec(path: Path) -> ModelSpec:
    """从 YAML 或 JSON 文件加载规格。读不了是 E_IO，内容不合法是 E_SCHEMA（消息点出错的字段）。"""
    return parse_model(ModelSpec, read_document(path), path.name)
