"""规范化：把 TaskSpec 变成 ModelSpec，或者一份问题清单。全部是纯函数。

分工：进料在 normalize_feeds.py，反应、候选产物和指标在 normalize_reactions.py，工况、热模式、
压降和物性包在 normalize_conditions.py，名字和物理量的换算在 quantities.py，组成的归一化在
composition.py，这里把它们拼起来。取了默认值的字段连同假设一起登记（notes.py），ModelSpec 自身的
校验没通过时，把 pydantic 的错误转成问题清单，不让异常抛出去。
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import ValidationError

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.components import ComponentTable
from reactor_agent.spec.enums import ReactorType
from reactor_agent.spec.loading import field_path
from reactor_agent.spec.model_spec import ModelSpec
from reactor_agent.spec.normalize_conditions import (
    check_drop_fits,
    normalize_cases,
    pressure_drop,
    property_package,
)
from reactor_agent.spec.normalize_feeds import FeedData, normalize_feeds
from reactor_agent.spec.normalize_reactions import (
    ReactionData,
    normalize_metrics,
    normalize_reactions,
    product_components,
)
from reactor_agent.spec.notes import Context
from reactor_agent.spec.results import Issue, make_issue
from reactor_agent.spec.task_spec import MissingField, MissingItem, TaskSpec, blocking_missing
from reactor_agent.spec.units import UnitTable

# 整个模型的校验器写的消息：“feeds[0].composition：……”。
ERROR_PATH = re.compile(r"^([A-Za-z_][\w\[\].]*)：(.*)$", re.DOTALL)
FEED_FIELD_PATHS: Mapping[MissingField, str] = {
    MissingField.FEED_TEMPERATURE: "temperature_c",
    MissingField.FEED_PRESSURE: "pressure_bar",
    MissingField.FEED_COMPOSITION: "composition",
    MissingField.FEED_FLOW: "flow",
}


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
    drop = pressure_drop(ctx, task)
    check_drop_fits(ctx, drop, feeds)
    cases = normalize_cases(ctx, task)
    package = property_package(ctx, task.property_package)
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
        "heat_mode": cases.heat_mode,
        "cases": cases.cases,
        "metrics": metrics,
        "assumptions": notes.assumptions(),
    }
    try:
        spec = ModelSpec.model_validate(data)
    except ValidationError as error:
        return Normalized(None, _validation_issues(error), defaulted, volume)
    return Normalized(spec, (), defaulted, volume)
