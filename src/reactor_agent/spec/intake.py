"""收下 LLM 写的 TaskSpec：抄写检查、规范化、通用业务规则，再加这种反应器专有的规则。

每一步都是纯函数。前一步有问题就不跑后一步（规范化出问题时没有 ModelSpec 可检查，抄写有问题时
规范化出来的数也没有意义；通用规则里的元素守恒和 Recipe 的规则有重叠，不让用户看到两条）。
spec 不能依赖 recipes，所以专有规则由调用方（VALIDATE 的处理函数）以函数的形式传进来。
"""

from collections.abc import Callable
from dataclasses import dataclass

from reactor_agent.spec.components import ComponentTable
from reactor_agent.spec.enums import ReactorType
from reactor_agent.spec.model_spec import ModelSpec
from reactor_agent.spec.normalize import normalize
from reactor_agent.spec.results import Issue
from reactor_agent.spec.rules import general_rules
from reactor_agent.spec.task_spec import TaskSpec
from reactor_agent.spec.transcription import transcription_issues
from reactor_agent.spec.units import UnitTable

SpecRules = Callable[[ModelSpec], tuple[Issue, ...]]


@dataclass(frozen=True)
class Intake:
    """收下的结果：通过了就是 ModelSpec，否则是问题清单。两者恰有一个。"""

    spec: ModelSpec | None
    issues: tuple[Issue, ...]


def intake(
    task: TaskSpec,
    text: str,
    reactor_type: ReactorType,
    tables: tuple[ComponentTable, UnitTable],
    reactor_rules: SpecRules,
) -> Intake:
    """TaskSpec 和用户原文 → ModelSpec，或者问题清单。tables 是组分表和单位表。"""
    components, units = tables
    normalized = normalize(task, reactor_type, components, units)
    issues = (*transcription_issues(task, text), *normalized.issues)
    spec = normalized.spec
    if issues or spec is None:
        return Intake(None, issues)
    found = general_rules(spec, components, normalized.defaulted_fields, normalized.volume_feeds)
    found = found or reactor_rules(spec)
    return Intake(None, found) if found else Intake(spec, ())
