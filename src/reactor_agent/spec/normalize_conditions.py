"""工况、热模式、压降和物性包的规范化。

热模式由各工况规定的量决定：都给出口温度、都给热负荷，或者都不给（绝热）。压降：用户给的；反应器
压力和进料自己的压力都给了就是它们的差（最低的进料压力减去反应器压力）；都没有就默认 0。
物性包：没有指定取 Peng-Robinson；指定了别的是问题，写法的差别（EOS、方程、连字符）不算别的。
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.enums import HeatMode, PressureBasis, PropertyPackage
from reactor_agent.spec.normalize_feeds import FeedData
from reactor_agent.spec.notes import Context
from reactor_agent.spec.quantities import DUTY, TEMPERATURE, convert_pressure, convert_value
from reactor_agent.spec.task_spec import CaseTask, Quantity, Source, TaskSpec
from reactor_agent.spec.units import to_pressure_bar

OUTLET_TEMPERATURE = "outlet_temperature_c"
DUTY_FIELD = "duty_kw"
DROP_PATH = "pressure_drop_bar"
REACTOR_PRESSURE_PATH = "reactor_pressure"
# 进料压力比反应器压力低这么多（bar）以内，当作相等；再低就是问题（反应器压力不能高于进料）。
PRESSURE_TOLERANCE_BAR = 1e-6
PACKAGE_SEPARATORS = re.compile(r"[\s_\-‐‑‒–—―−]")
# “Peng-Robinson (PR)”：括号里的缩写和括号外的全名都是同一个包。
PACKAGE_BRACKETS = re.compile(r"[()\[\]]")
PACKAGE_NAMES = frozenset({"pr", "pengrobinson", "pengrob", "彭罗宾逊"})
# 写在物性包名字后面的通用词，去掉再比较：“Peng-Robinson EOS”“PR 状态方程”。
GENERIC_SUFFIXES = ("equationofstate", "propertypackage", "eos", "状态方程", "物性包", "方程")


@dataclass(frozen=True)
class CaseSet:
    """工况：热模式，和每个工况的规格（字典，最后由 ModelSpec 校验）。"""

    heat_mode: HeatMode
    cases: tuple[dict[str, object], ...]


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
    if only and task.adiabatic_stated:
        message = "原文说了绝热操作，又给了出口温度或热负荷：只能是其中一种"
        ctx.notes.problem(ErrorCode.SCHEMA, "cases", message)
        return None
    if only == {OUTLET_TEMPERATURE}:
        return HeatMode.SPECIFIED_OUTLET_TEMPERATURE
    if only == {DUTY_FIELD}:
        return HeatMode.SPECIFIED_DUTY
    if task.adiabatic_stated:
        return HeatMode.ADIABATIC
    reason = "原文没有给出口温度，也没有给热负荷，按绝热，出口温度作为结果"
    return ctx.notes.default("heat_mode", HeatMode.ADIABATIC, reason)


def normalize_cases(ctx: Context, task: TaskSpec) -> CaseSet | None:
    """各工况的规格和热模式。没有工况、工况的规定方式不一致、换算出了问题都是 None。"""
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
    cases = tuple(
        {"name": case.name, **values} for case, values in zip(task.cases, given, strict=True)
    )
    return CaseSet(mode, cases)


def _drop_between(ctx: Context, task: TaskSpec) -> float | None:
    """反应器压力和进料自己的压力都给了：压降是最低的进料压力减去反应器压力。

    没有自己压力的进料取反应器压力（见 normalize_feeds），所以有这样的进料时，最低的进料压力
    就是反应器压力，压降是 0。
    """
    reactor = task.reactor_pressure
    own = [(i, feed.pressure) for i, feed in enumerate(task.feeds) if feed.pressure is not None]
    if reactor is None or not own:
        return None
    inherits = len(own) < len(task.feeds)
    # 进料自己的压力的基准假设已经登记在各自的字段上；反应器压力没有被进料用到时，登记在压降上。
    reactor_bar = convert_pressure(
        ctx, reactor, REACTOR_PRESSURE_PATH, None if inherits else DROP_PATH
    )
    converted = [convert_pressure(ctx, q, f"feeds[{i}].pressure_bar") for i, q in own]
    feed_bars = [bar for bar in converted if bar is not None]
    if reactor_bar is None or len(feed_bars) != len(converted):
        return None
    lowest = min([*feed_bars, reactor_bar] if inherits else feed_bars)
    if lowest < reactor_bar - PRESSURE_TOLERANCE_BAR:
        message = f"反应器压力 {reactor_bar:g} bar 高于进料压力 {lowest:g} bar，压降会是负的"
        ctx.notes.problem(ErrorCode.RULE, DROP_PATH, message, user_fixable=True)
        return None
    return max(lowest - reactor_bar, 0.0)


def _given_drop(ctx: Context, drop: Quantity) -> float | None:
    bar = to_pressure_bar(ctx.units, drop.value, drop.unit, PressureBasis.ABSOLUTE)
    if bar is None or bar < 0:
        message = f"压降 {drop.value:g} {drop.unit} 的单位不认识，或者是负数"
        ctx.notes.problem(ErrorCode.RULE, DROP_PATH, message, user_fixable=True)
        return None
    if drop.source is Source.ASSUMED:
        ctx.notes.declare(DROP_PATH, f"{drop.value:g} {drop.unit}", drop.rationale or "")
    return bar


def pressure_drop(ctx: Context, task: TaskSpec) -> float | None:
    """压降：用户给的；反应器压力和进料压力都给了就是它们的差；都没有就默认 0（登记假设）。"""
    if task.pressure_drop is not None:
        return _given_drop(ctx, task.pressure_drop)
    between = _drop_between(ctx, task)
    if between is not None:
        return between
    return ctx.notes.default(DROP_PATH, 0.0, "原文没有给压降，按 0")


def check_drop_fits(ctx: Context, drop: float | None, feeds: Sequence[FeedData]) -> None:
    """压降要小于最低的进料压力，否则出口压力不是正数（到 HYSYS 里才会暴露）。"""
    if drop is None or not feeds:
        return
    lowest = min(feed.pressure_bar for feed in feeds)
    if drop >= lowest:
        message = f"压降 {drop:g} bar 不小于最低的进料压力 {lowest:g} bar，出口压力不是正数"
        ctx.notes.problem(ErrorCode.RULE, DROP_PATH, message, user_fixable=True)


def _package_key(text: str) -> str:
    key = PACKAGE_SEPARATORS.sub("", text.casefold())
    stripped = True
    while stripped:
        stripped = False
        for suffix in GENERIC_SUFFIXES:
            if key.endswith(suffix) and len(key) > len(suffix):
                key, stripped = key[: -len(suffix)], True
    return key


def _is_peng_robinson(text: str) -> bool:
    """写法的各部分（括号里的缩写算一部分，单独的“方程”“EOS”不算）都是 Peng-Robinson。"""
    normalized = unicodedata.normalize("NFKC", text)
    keys = [_package_key(part) for part in PACKAGE_BRACKETS.split(normalized) if part.strip()]
    named = [key for key in keys if key not in GENERIC_SUFFIXES]
    return bool(named) and all(key in PACKAGE_NAMES for key in named)


def property_package(ctx: Context, requested: str | None) -> PropertyPackage | None:
    """物性包：没有指定取 Peng-Robinson（登记假设，目前唯一验证过的）；指定了别的是问题。"""
    if requested is None:
        reason = "原文没有指定物性包，取 Peng-Robinson（目前唯一验证过的）"
        return ctx.notes.default("property_package", PropertyPackage.PENG_ROBINSON, reason)
    if _is_peng_robinson(requested):
        return PropertyPackage.PENG_ROBINSON
    message = f"物性包 {requested!r} 目前不支持，只支持 Peng-Robinson"
    ctx.notes.problem(ErrorCode.RULE, "property_package", message, user_fixable=True)
    return None
