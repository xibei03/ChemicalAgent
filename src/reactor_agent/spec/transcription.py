"""抄写检查：LLM 写下的“用户给的数”，是不是原文里真有的数。

“数值照原文抄，不换算，不做算术”是一条机械检查得出的约束：LLM 把 2.5 MPa 换成 25 却保留单位 MPa 时，
没有别的检查能发现，HYSYS 里的压力会差一个数量级。来源是用户的数值，必须出现在原文里（全角半角统一，
千分位去掉）。原文里没有阿拉伯数字（数字都用汉字写）时不查；只有一个组分的组成，份额恒为 1，不查。
"""

import math
import re
import unicodedata
from collections.abc import Iterator

from reactor_agent.errors import ErrorCode
from reactor_agent.spec.results import Issue, make_issue
from reactor_agent.spec.task_spec import (
    ConversionReactionTask,
    EquilibriumReactionTask,
    GibbsTaskSpec,
    Quantity,
    Source,
    TaskSpec,
)

NUMBER = re.compile(r"\d+(?:\.\d+)?")
THOUSANDS_SEPARATOR = re.compile(r"(?<=\d),(?=\d{3})")
RELATIVE_TOLERANCE = 1e-9
# 只有一个组分的组成，份额恒为 1，不需要在原文里出现。
MIN_ITEMS_TO_CHECK = 2


def numbers_in(text: str) -> tuple[float, ...]:
    """文字里出现的全部数（非负）。"""
    cleaned = THOUSANDS_SEPARATOR.sub("", unicodedata.normalize("NFKC", text))
    return tuple(float(match) for match in NUMBER.findall(cleaned))


def _quantities(task: TaskSpec) -> Iterator[tuple[str, Quantity | None]]:
    for index, feed in enumerate(task.feeds):
        yield f"feeds[{index}].temperature_c", feed.temperature
        yield f"feeds[{index}].pressure_bar", feed.pressure
        yield f"feeds[{index}].flow", feed.flow
    yield "reactor_pressure", task.reactor_pressure
    yield "pressure_drop_bar", task.pressure_drop
    for index, case in enumerate(task.cases):
        yield f"cases[{index}].outlet_temperature_c", case.outlet_temperature
        yield f"cases[{index}].duty_kw", case.duty


def _composition_claims(task: TaskSpec) -> Iterator[tuple[str, float]]:
    for index, feed in enumerate(task.feeds):
        composition = feed.composition
        if composition is None or composition.source is not Source.USER:
            continue
        if len(composition.items) < MIN_ITEMS_TO_CHECK:
            continue
        for k, item in enumerate(composition.items):
            if item.amount is not None:
                yield f"feeds[{index}].composition.items[{k}]", item.amount


def _reaction_claims(task: TaskSpec) -> Iterator[tuple[str, float]]:
    if isinstance(task, GibbsTaskSpec):
        return
    for index, reaction in enumerate(task.reactions):
        if isinstance(reaction, ConversionReactionTask):
            conversion = reaction.conversion
            if conversion is not None and conversion.source is Source.USER:
                yield f"reactions[{index}].conversion_percent", conversion.value
        elif isinstance(reaction, EquilibriumReactionTask) and reaction.equilibrium_constant:
            yield f"reactions[{index}].equilibrium_constant", reaction.equilibrium_constant


def _claimed(task: TaskSpec) -> Iterator[tuple[str, float]]:
    """LLM 声称是用户给的数：路径和数值。"""
    for path, quantity in _quantities(task):
        if quantity is not None and quantity.source is Source.USER:
            yield path, quantity.value
    yield from _composition_claims(task)
    yield from _reaction_claims(task)


def transcription_issues(task: TaskSpec, text: str) -> tuple[Issue, ...]:
    """来源是用户的数值，原文里找不到的，每个是一个问题。"""
    found = numbers_in(text)
    if not found:
        return ()
    return tuple(
        make_issue(
            ErrorCode.SCHEMA,
            path,
            f"数值 {value:g} 在原文里找不到。用户给的数要照原文抄，不要换算，也不要自己做算术；"
            "原文没有给的量，来源写 assumed（可以假设的）或者写 null 并列进 missing",
        )
        for path, value in _claimed(task)
        if not any(math.isclose(abs(value), number, rel_tol=RELATIVE_TOLERANCE) for number in found)
    )
