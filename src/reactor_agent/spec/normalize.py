"""规范化：把 TaskSpec 变成 ModelSpec，或者一份问题清单。全部是纯函数。

分工：进料在 normalize_feeds.py，反应、候选产物和指标在 normalize_reactions.py，名字和物理量的
换算在 quantities.py，组成的归一化在 composition.py，这里把它们拼起来，并处理工况、热模式、压降和
物性包。取了默认值的字段连同假设一起登记（notes.py），ModelSpec 自身的校验没通过时，把 pydantic
的错误转成问题清单，不让异常抛出去。
"""

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import ValidationError

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.components import ComponentTable
from reactor_agent.spec.enums import HeatMode, PressureBasis, PropertyPackage, ReactorType
from reactor_agent.spec.loading import field_path
from reactor_agent.spec.model_spec import ModelSpec
from reactor_agent.spec.normalize_feeds import FeedData, normalize_feeds
from reactor_agent.spec.normalize_reactions import (
    ReactionData,
    normalize_metrics,
    normalize_reactions,
    product_components,
)
from reactor_agent.spec.notes import Context
from reactor_agent.spec.quantities import DUTY, TEMPERATURE, convert_pressure, convert_value
from reactor_agent.spec.results import Issue, make_issue
from reactor_agent.spec.task_spec import (
    CaseTask,
    MissingField,
    MissingItem,
    Quantity,
    Source,
    TaskSpec,
    blocking_missing,
)
from reactor_agent.spec.units import UnitTable, to_pressure_bar

PACKAGE_SEPARATORS = re.compile(r"[\s_\-]")
# 整个模型的校验器写的消息：“feeds[0].composition：……”。
ERROR_PATH = re.compile(r"^([A-Za-z_][\w\[\].]*)：(.*)$", re.DOTALL)
PROPERTY_PACKAGE_NAMES: Mapping[str, PropertyPackage] = {
    "pengrobinson": PropertyPackage.PENG_ROBINSON,
    "pengrob": PropertyPackage.PENG_ROBINSON,
    "pr": PropertyPackage.PENG_ROBINSON,
    "彭罗宾逊": PropertyPackage.PENG_ROBINSON,
}
FEED_FIELD_PATHS: Mapping[MissingField, str] = {
    MissingField.FEED_TEMPERATURE: "temperature_c",
    MissingField.FEED_PRESSURE: "pressure_bar",
    MissingField.FEED_COMPOSITION: "composition",
    MissingField.FEED_FLOW: "flow",
}
OUTLET_TEMPERATURE = "outlet_temperature_c"
DUTY_FIELD = "duty_kw"
# 进料压力比反应器压力低这么多（bar）以内，当作相等；再低就是问题（反应器压力不能高于进料）。
PRESSURE_TOLERANCE_BAR = 1e-6


@dataclass(frozen=True)
class Normalized:
    """规范化的结果：ModelSpec（有问题时是 None）、问题、取了默认值的字段、标准体积流量的进料。"""

    spec: ModelSpec | None
    issues: tuple[Issue, ...]
    defaulted_fields: tuple[str, ...]
    volume_feeds: tuple[int, ...]


def missing_path(item: MissingItem) -> str:
    """一条缺失信息在规格里的字段路径。"""
    suffix = FEED_FIELD_PATHS.get(item.field)
    if suffix is not None:
        return f"feeds[{item.feed_index or 0}].{suffix}"
    return "missing" if item.field is MissingField.OTHER else "reactions"


def _declared_missing(ctx: Context, task: TaskSpec) -> None:
    """LLM 声明的缺失信息：不可以假设的，每条是一个问题（可以假设的由取值和依据处理）。"""
    for item in blocking_missing(task):
        message = f"缺少关键信息：{item.description}"
        ctx.notes.problem(ErrorCode.RULE, missing_path(item), message, user_fixable=True)


def _case_values(ctx: Context, case: CaseTask, path: str) -> dict[str, float] | None:
    """一个工况规定的量：出口温度（°C）和热负荷（kW），没有规定的不出现。换算出了问题是 None。"""
    values: dict[str, float] = {}
    for key, quantity, kind in (
        (OUTLET_TEMPERATURE, case.outlet_temperature, TEMPERATURE),
        (DUTY_FIELD, case.duty, DUTY),
    ):
        if quantity is None:
            continue
        converted = convert_value(ctx, quantity, f"{path}.{key}", kind)
        if converted is None:
            return None
        values[key] = converted
    return values


def _heat_mode(ctx: Context, task: TaskSpec, given: list[dict[str, float]]) -> HeatMode | None:
    """各工况规定的量决定热模式。都不规定时取绝热：原文说了绝热就不是假设，否则登记假设。"""
    kinds = {frozenset(values) for values in given}
    if len(kinds) != 1 or len(next(iter(kinds))) > 1:
        message = (
            "各工况的规定方式要一致：都给出口温度、都给热负荷，或者都不给；一个工况不能同时给两个量"
        )
        ctx.notes.problem(ErrorCode.SCHEMA, "cases", message)
        return None
    (only,) = kinds
    if only == {OUTLET_TEMPERATURE}:
        return HeatMode.SPECIFIED_OUTLET_TEMPERATURE
    if only == {DUTY_FIELD}:
        return HeatMode.SPECIFIED_DUTY
    if task.adiabatic_stated:
        return HeatMode.ADIABATIC
    reason = "原文没有给出口温度，也没有给热负荷，按绝热，出口温度作为结果"
    return ctx.notes.default("heat_mode", HeatMode.ADIABATIC, reason)


def _cases(ctx: Context, task: TaskSpec) -> tuple[HeatMode, list[dict[str, object]]] | None:
    if not task.cases:
        ctx.notes.problem(ErrorCode.SCHEMA, "cases", "没有工况：至少写一个")
        return None
    found = [_case_values(ctx, case, f"cases[{index}]") for index, case in enumerate(task.cases)]
    given = [values for values in found if values is not None]
    if len(given) != len(found):
        return None
    mode = _heat_mode(ctx, task, given)
    if mode is None:
        return None
    cases: list[dict[str, object]] = [
        {"name": case.name, **values} for case, values in zip(task.cases, given, strict=True)
    ]
    return mode, cases


def _drop_between(ctx: Context, task: TaskSpec) -> float | None:
    """进料压力和反应器压力都给了：压降是它们的差。反应器压力高于进料压力是问题。"""
    path = "pressure_drop_bar"
    own = next((feed.pressure for feed in task.feeds if feed.pressure is not None), None)
    if own is None or task.reactor_pressure is None:
        return None
    feed_bar = convert_pressure(ctx, own, path)
    reactor_bar = convert_pressure(ctx, task.reactor_pressure, path)
    if feed_bar is None or reactor_bar is None:
        return None
    if feed_bar < reactor_bar - PRESSURE_TOLERANCE_BAR:
        message = f"反应器压力 {reactor_bar:g} bar 高于进料压力 {feed_bar:g} bar，压降会是负的"
        ctx.notes.problem(ErrorCode.RULE, path, message, user_fixable=True)
        return None
    return max(feed_bar - reactor_bar, 0.0)


def _given_drop(ctx: Context, drop: Quantity) -> float | None:
    path = "pressure_drop_bar"
    bar = to_pressure_bar(ctx.units, drop.value, drop.unit, PressureBasis.ABSOLUTE)
    if bar is None or bar < 0:
        message = f"压降 {drop.value:g} {drop.unit} 的单位不认识，或者是负数"
        ctx.notes.problem(ErrorCode.RULE, path, message, user_fixable=True)
        return None
    if drop.source is Source.ASSUMED:
        ctx.notes.declare(path, f"{drop.value:g} {drop.unit}", drop.rationale or "")
    return bar


def _pressure_drop(ctx: Context, task: TaskSpec) -> float | None:
    """压降：用户给的；进料和反应器压力都给了就是它们的差；都没有就默认 0（登记假设）。"""
    if task.pressure_drop is not None:
        return _given_drop(ctx, task.pressure_drop)
    between = _drop_between(ctx, task)
    if between is not None:
        return between
    return ctx.notes.default("pressure_drop_bar", 0.0, "原文没有给压降，按 0")


def _property_package(ctx: Context, requested: str | None) -> PropertyPackage | None:
    """物性包：没有指定取 Peng-Robinson（登记假设，目前唯一验证过的）；指定了别的是问题。"""
    if requested is None:
        reason = "原文没有指定物性包，取 Peng-Robinson（目前唯一验证过的）"
        return ctx.notes.default("property_package", PropertyPackage.PENG_ROBINSON, reason)
    key = PACKAGE_SEPARATORS.sub("", unicodedata.normalize("NFKC", requested)).casefold()
    package = PROPERTY_PACKAGE_NAMES.get(key)
    if package is None:
        message = f"物性包 {requested!r} 目前不支持，只支持 Peng-Robinson"
        ctx.notes.problem(ErrorCode.RULE, "property_package", message, user_fixable=True)
    return package


def _validation_issues(error: ValidationError) -> tuple[Issue, ...]:
    """ModelSpec 自身的校验错误转成问题清单（结构问题，E_SCHEMA）。

    整个模型的校验器抛的错误没有位置，但消息以“字段路径：”开头，路径从消息里取。元素本身出了错
    以后，容器“至少要有 1 项”的错误只是它的后果，不单独报。
    """
    errors = error.errors()
    issues = []
    for item in errors:
        location = tuple(item["loc"])
        if item["type"] == "too_short" and any(
            other["loc"][: len(location)] == location and other is not item for other in errors
        ):
            continue
        message = item["msg"].removeprefix("Value error, ")
        path = field_path(location)
        named = ERROR_PATH.match(message) if not location else None
        if named is not None:
            path, message = named.group(1), named.group(2)
        issues.append(make_issue(ErrorCode.SCHEMA, path, message))
    return tuple(issues)


def _components(
    feeds: list[FeedData], reactions: list[ReactionData], products: tuple[str, ...]
) -> list[str]:
    names = [name for feed in feeds for name in feed.components]
    names += [name for reaction in reactions for name in reaction.components]
    return list(dict.fromkeys([*names, *products]))


def normalize(
    task: TaskSpec, reactor_type: ReactorType, table: ComponentTable, units: UnitTable
) -> Normalized:
    """TaskSpec → ModelSpec，或者问题清单。reactor_type 来自选型结论，LLM 改不了。"""
    ctx = Context(table, units)
    _declared_missing(ctx, task)
    feeds = normalize_feeds(ctx, task.feeds, task.reactor_pressure)
    reactions = normalize_reactions(ctx, task)
    products = product_components(ctx, task)
    drop = _pressure_drop(ctx, task)
    cases = _cases(ctx, task)
    package = _property_package(ctx, task.property_package)
    metrics = normalize_metrics(ctx, task)
    for item in task.assumptions:
        ctx.notes.declare(item.field.value, item.statement, item.rationale)
    notes = ctx.notes
    defaulted, volume = tuple(notes.defaulted), tuple(notes.volume_feeds)
    if notes.issues or cases is None:
        return Normalized(None, tuple(notes.issues), defaulted, volume)
    data: dict[str, object] = {
        "reactor_type": reactor_type,
        "property_package": package,
        "components": _components(feeds, reactions, products),
        "feeds": [feed.spec for feed in feeds],
        "reactions": [reaction.spec for reaction in reactions],
        "pressure_drop_bar": drop,
        "heat_mode": cases[0],
        "cases": cases[1],
        "metrics": metrics,
        "assumptions": notes.assumptions(),
    }
    try:
        spec = ModelSpec.model_validate(data)
    except ValidationError as error:
        return Normalized(None, _validation_issues(error), defaulted, volume)
    return Normalized(spec, (), defaulted, volume)
