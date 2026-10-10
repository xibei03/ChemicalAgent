"""组分表：HYSYS 规范名、别名、分子式、分子量和常温常压下的相态。

规范名必须是 HYSYS 组分库里实测过的名字（台账“组分规范名”一节）。分子式解析成“元素 → 原子数”，
供元素守恒检查使用。文件路径由调用方传入，这里不猜路径。
"""

import difflib
import re
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import ComponentPhase
from reactor_agent.spec.loading import parse_model, read_document
from reactor_agent.spec.tool_args import FeedConditions

# 水的分子式：干基组成要扣除它，气化的进料要有它。
WATER_FORMULA = "H2O"
# 元素符号加个数，或者括号的开和闭（闭括号后面可以跟倍数）。
FORMULA_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)|(\()|(\))(\d*)")
# “甲烷 (CH4)”这类带说明的写法，按这些符号拆开再找。
NAME_SEPARATORS = re.compile(r"[()（）/、,;；]")
MAX_CANDIDATES = 3
CANDIDATE_CUTOFF = 0.5
PHASE_TEXT: Mapping[ComponentPhase, str] = {
    ComponentPhase.GAS: "气",
    ComponentPhase.LIQUID: "液",
    ComponentPhase.SOLID: "固",
}


def _merge(target: dict[str, int], source: Mapping[str, int], factor: int) -> None:
    for symbol, atoms in source.items():
        target[symbol] = target.get(symbol, 0) + atoms * factor


def parse_formula(formula: str) -> Mapping[str, int]:
    """把分子式变成“元素 → 原子数”，支持括号，如 Ca(OH)2。写法不对抛 ValueError。"""
    groups: list[dict[str, int]] = [{}]
    text = formula.strip()
    position = 0
    while position < len(text):
        match = FORMULA_TOKEN.match(text, position)
        if match is None:
            raise ValueError(f"分子式 {formula!r} 的第 {position + 1} 个字符不认识")
        position = match.end()
        element, count, opening, closing, multiplier = match.groups()
        if opening:
            groups.append({})
        elif closing:
            if len(groups) == 1:
                raise ValueError(f"分子式 {formula!r} 有多余的右括号")
            _merge(groups[-2], groups.pop(), int(multiplier or 1))
        else:
            _merge(groups[-1], {element: 1}, int(count or 1))
    if len(groups) != 1 or not groups[0]:
        raise ValueError(f"分子式 {formula!r} 的括号没有闭合，或者是空的")
    return groups[0]


def normalize_name(text: str) -> str:
    """名字比较前的规范化：全角半角统一、去掉首尾空白、不分大小写。"""
    return unicodedata.normalize("NFKC", text).strip().casefold()


class ComponentEntry(FrozenModel):
    """一个组分。name 是 HYSYS 规范名，aliases 是中文和英文别名。"""

    name: Annotated[str, Field(min_length=1)]
    aliases: tuple[str, ...] = ()
    formula: str
    molecular_weight_kg_per_kmol: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    phase: ComponentPhase

    @field_validator("formula")
    @classmethod
    def _formula_is_parsable(cls, value: str) -> str:
        parse_formula(value)
        return value


class ComponentTable(FrozenModel):
    """组分表。名字和别名（规范化之后）不能同时指向两个组分。"""

    components: tuple[ComponentEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _names_are_unambiguous(self) -> Self:
        owners: dict[str, str] = {}
        for entry in self.components:
            for text in (entry.name, *entry.aliases):
                owner = owners.setdefault(normalize_name(text), entry.name)
                if owner != entry.name:
                    raise ValueError(f"{text!r} 同时是 {owner} 和 {entry.name} 的名字或别名")
        return self


def find_component(table: ComponentTable, text: str) -> ComponentEntry | None:
    """按规范名或别名找组分；找不到是 None。"""
    key = normalize_name(text)
    for entry in table.components:
        if key in {normalize_name(name) for name in (entry.name, *entry.aliases)}:
            return entry
    return None


def resolve_component(table: ComponentTable, text: str) -> ComponentEntry | None:
    """找组分：整个写法先找；带说明的写法（“甲烷 (CH4)”）拆开后各部分指向同一个组分也算。"""
    entry = find_component(table, text)
    if entry is not None:
        return entry
    matches = (find_component(table, part) for part in NAME_SEPARATORS.split(text) if part.strip())
    found = {match.name: match for match in matches if match is not None}
    return next(iter(found.values())) if len(found) == 1 else None


def closest_names(table: ComponentTable, text: str) -> tuple[str, ...]:
    """名字最接近 text 的几个组分的规范名，解析不了时给人和 LLM 看。可能一个都没有。"""
    spellings = {normalize_name(n): e.name for e in table.components for n in (e.name, *e.aliases)}
    close = difflib.get_close_matches(
        normalize_name(text), list(spellings), n=MAX_CANDIDATES * 2, cutoff=CANDIDATE_CUTOFF
    )
    return tuple(dict.fromkeys(spellings[spelling] for spelling in close))[:MAX_CANDIDATES]


def component_reference(table: ComponentTable) -> str:
    """给 LLM 的组分命名参考：每个组分的规范名、分子式、常温常压下的相态和常见称呼。"""
    lines = ["| 规范名 | 分子式 | 相态 | 常见称呼 |", "|---|---|---|---|"]
    for entry in table.components:
        phase, aliases = PHASE_TEXT[entry.phase], "、".join(entry.aliases)
        lines.append(f"| {entry.name} | {entry.formula} | {phase} | {aliases} |")
    return "\n".join(lines)


def names_with_formula(table: ComponentTable, formula: str) -> tuple[str, ...]:
    """分子式等于给定写法的组分的规范名，如 H2O。按“元素 → 原子数”比较，所以写法的顺序无关。"""
    wanted = parse_formula(formula)
    return tuple(e.name for e in table.components if parse_formula(e.formula) == wanted)


def molecular_weights(table: ComponentTable) -> Mapping[str, float]:
    """每个组分（规范名）的分子量，kg/kmol。"""
    return {entry.name: entry.molecular_weight_kg_per_kmol for entry in table.components}


def feed_molar_flow_kmol_h(feed: FeedConditions, table: ComponentTable) -> float:
    """进料的摩尔流量：给了摩尔流量就用它，给的是质量流量就除以平均分子量。"""
    if feed.molar_flow_kmol_h is not None:
        return feed.molar_flow_kmol_h
    mass_flow = feed.mass_flow_kg_h
    if mass_flow is None:
        raise ReactorAgentError(ErrorCode.SCHEMA, "进料没有给出摩尔流量，也没有给出质量流量")
    weights = molecular_weights(table)
    mean_weight = sum(item.mole_fraction * weights[item.component] for item in feed.composition)
    return mass_flow / mean_weight


def is_solid(table: ComponentTable, name: str) -> bool:
    """组分在常温常压下是固体。不在组分表里的组分不算。"""
    entry = find_component(table, name)
    return entry is not None and entry.phase is ComponentPhase.SOLID


def atoms_by_component(table: ComponentTable) -> Mapping[str, Mapping[str, int]]:
    """每个组分（规范名）的“元素 → 原子数”。"""
    return {entry.name: parse_formula(entry.formula) for entry in table.components}


def load_component_table(path: Path) -> ComponentTable:
    """从 YAML 或 JSON 文件加载组分表。文件读不了是 E_IO，内容不合法是 E_SCHEMA。"""
    return parse_model(ComponentTable, read_document(path), path.name)
