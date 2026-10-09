"""选型的纯函数：原文依据检查、规则检查、与 LLM 推荐的对照、组装最终结果。

不读文件，不调 LLM。规则表由 skill_loader 读成 SelectionRules 再传进来。PFR 与 CSTR 之间怎么选、
聚合反应的例外是需求 §8 的内容，不随规则表变化，所以写在这里。
"""

import unicodedata
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import ReactorType
from reactor_agent.spec.selection import (
    FEATURE_LABELS,
    REACTOR_NAMES,
    Alternative,
    Decision,
    EquipmentForm,
    FeatureName,
    FeedPhase,
    Flag,
    PriorityRule,
    PriorityRuleId,
    RuleVerdict,
    SelectionDraft,
    SelectionFeatures,
    SelectionResult,
    SelectionRules,
    Unbuildable,
)

NOT_A_REACTION_NOTE = "不是反应过程的模拟请求，没有需要选择的反应器。"
MISSING_SIZE_NOTE = "设备尺寸（体积、管长、管径）没有给出：不影响选型，建模前需要补充。"
POLYMER_EXCEPTION_NOTE = (
    "给出了动力学参数，但这是聚合反应：需求 §8 规定动力学反应器的规则不适用于聚合反应，"
    "跳过这一条（规定的例外）。"
)
KINETIC_NOTE_PREFIX = "给出了动力学参数，选动力学反应器："
LOWER_PRIORITY_REASON = "优先级低于所选类型"
LLM_RECOMMENDED_PREFIX = "LLM 推荐过它，规则没有采纳："
# 动力学反应器之间的选择（需求 §8 第 3 条和第 1 条的默认值）。
FORM_CHOICE: Mapping[EquipmentForm, ReactorType] = MappingProxyType(
    {EquipmentForm.TUBULAR: ReactorType.PFR, EquipmentForm.VESSEL: ReactorType.CSTR}
)
PHASE_CHOICE: Mapping[FeedPhase, ReactorType] = MappingProxyType(
    {FeedPhase.GAS: ReactorType.PFR, FeedPhase.LIQUID: ReactorType.CSTR}
)
# 建模需要设备尺寸的类型：尺寸缺失不影响选型，但要在结论里指出。
SIZED_REACTORS = frozenset({ReactorType.PFR, ReactorType.CSTR})
# 命中时的说明。{name} 换成选出的类型。
HIT_NOTES: Mapping[PriorityRuleId, str] = MappingProxyType(
    {
        PriorityRuleId.NAMED_REACTOR: "用户点名了 {name}，必要输入齐备，采纳。",
        PriorityRuleId.CONVERSION: "给出了转化率、收率或选择性的数值，选 {name}。",
        PriorityRuleId.BLACK_BOX: "黑箱类体系，产物分布由热力学平衡决定，选 {name}。",
        PriorityRuleId.EQUILIBRIUM: "反应已明确，平衡由 Keq 或 Gibbs 自由能确定，选 {name}。",
    }
)


def normalize_text(text: str) -> str:
    """比较原文依据之前的规范化：NFKC（全角半角、上下标、℃ 与 °C 等同），再去掉全部空白。"""
    return "".join(unicodedata.normalize("NFKC", text).split())


def _quoted(evidence: str, text: str) -> bool:
    wanted = normalize_text(evidence)
    return bool(wanted) and wanted in normalize_text(text)


def invalid_evidence(features: SelectionFeatures, text: str) -> tuple[str, ...]:
    """引用了但在原文里找不到的依据。"""
    return tuple(quote.text for quote in features.quotes() if not _quoted(quote.text, text))


def drop_invalid_evidence(features: SelectionFeatures, text: str) -> SelectionFeatures:
    """丢掉不是原文原话的依据，特征的取值不变。"""

    def valid(evidence: str | None) -> str | None:
        return evidence if evidence is not None and _quoted(evidence, text) else None

    flags = {
        name.value: Flag(value=flag.value, evidence=valid(flag.evidence))
        for name in FeatureName
        if (flag := features.flag(name)).value
    }
    named = features.named_reactor.model_copy(
        update={"evidence": valid(features.named_reactor.evidence)}
    )
    return features.model_copy(update={**flags, "named_reactor": named})


@dataclass(frozen=True)
class _Situation:
    """应用一条第二层规则时看到的一切。"""

    features: SelectionFeatures
    buildable: tuple[ReactorType, ...]
    unbuildable: Mapping[ReactorType, tuple[FeatureName, ...]]
    llm_choice: ReactorType | None
    rule: PriorityRule


@dataclass(frozen=True)
class _Step:
    """一条规则的处理结果：命中了就有 picked；note 是命中的说明，或者没命中时值得说明的原因。"""

    picked: ReactorType | None
    note: str | None = None


def _missing_text(missing: tuple[FeatureName, ...]) -> str:
    return "、".join(FEATURE_LABELS[name] for name in missing)


def _named(situation: _Situation) -> _Step:
    named = situation.features.named_reactor.reactor_type
    if named is None:
        return _Step(None)
    if named in situation.buildable:
        return _Step(named, HIT_NOTES[PriorityRuleId.NAMED_REACTOR])
    lacking = _missing_text(situation.unbuildable[named])
    return _Step(
        None, f"用户点名了 {REACTOR_NAMES[named]}，但缺少：{lacking}，不采纳，继续往下判断。"
    )


def _choose_kinetic(
    features: SelectionFeatures, candidates: tuple[ReactorType, ...], llm_choice: ReactorType | None
) -> _Step:
    by_form = FORM_CHOICE.get(features.equipment_form)
    if by_form in candidates:
        return _Step(by_form, f"设备形式是{_form_text(features.equipment_form)}，选 {{name}}。")
    by_phase = PHASE_CHOICE.get(features.phase)
    if by_phase in candidates:
        return _Step(
            by_phase, f"没有说明设备形式，反应物是{_phase_text(features.phase)}，选 {{name}}。"
        )
    if llm_choice in candidates:
        return _Step(llm_choice, "设备形式和相态都定不了，采用 LLM 的推荐 {name}。")
    return _Step(candidates[0], "设备形式和相态都定不了，LLM 也没有推荐动力学反应器，取 {name}。")


def _form_text(form: EquipmentForm) -> str:
    return "管式" if form is EquipmentForm.TUBULAR else "釜式"


def _phase_text(phase: FeedPhase) -> str:
    return "气相" if phase is FeedPhase.GAS else "液相"


def _kinetic(situation: _Situation) -> _Step:
    candidates = tuple(c for c in situation.rule.candidates if c in situation.buildable)
    if not candidates:
        return _Step(None)
    if situation.features.polymerization.value:
        return _Step(None, POLYMER_EXCEPTION_NOTE)
    chosen = _choose_kinetic(situation.features, candidates, situation.llm_choice)
    return _Step(chosen.picked, KINETIC_NOTE_PREFIX + (chosen.note or ""))


def _by_table(situation: _Situation) -> _Step:
    """其余几条规则：条件特征为是，并且候选里有能建的，就取第一个能建的。"""
    condition = situation.rule.when
    if condition is not None and not situation.features.flag(condition).value:
        return _Step(None)
    for candidate in situation.rule.candidates:
        if candidate in situation.buildable:
            return _Step(candidate, HIT_NOTES[situation.rule.rule])
    return _Step(None)


_APPLIERS: Mapping[PriorityRuleId, Callable[[_Situation], _Step]] = MappingProxyType(
    {
        PriorityRuleId.NAMED_REACTOR: _named,
        PriorityRuleId.KINETIC: _kinetic,
        PriorityRuleId.CONVERSION: _by_table,
        PriorityRuleId.BLACK_BOX: _by_table,
        PriorityRuleId.EQUILIBRIUM: _by_table,
    }
)


def _split_by_requirements(
    features: SelectionFeatures, rules: SelectionRules
) -> tuple[tuple[ReactorType, ...], dict[ReactorType, tuple[FeatureName, ...]]]:
    """能建的类型，以及不能建的类型各缺哪些特征。"""
    buildable = []
    lacking = {}
    for kind in ReactorType:
        missing = tuple(n for n in rules.requirements[kind] if not features.flag(n).value)
        if missing:
            lacking[kind] = missing
        else:
            buildable.append(kind)
    return tuple(buildable), lacking


def _buildable_note(
    buildable: tuple[ReactorType, ...], lacking: Mapping[ReactorType, tuple[FeatureName, ...]]
) -> str:
    text = f"能建的类型：{'、'.join(REACTOR_NAMES[kind] for kind in buildable)}。"
    if lacking:
        parts = [f"{REACTOR_NAMES[k]}（缺：{_missing_text(m)}）" for k, m in lacking.items()]
        text += f"不能建的类型：{'、'.join(parts)}。"
    return text


@dataclass(frozen=True)
class _Hit:
    """第二层的结论：选了哪个类型，以及它是第几条规则（fallback 排在表的最后一条之后）。"""

    reactor_type: ReactorType
    number: int


def _walk_priority(
    features: SelectionFeatures,
    rules: SelectionRules,
    buildable: tuple[ReactorType, ...],
    lacking: Mapping[ReactorType, tuple[FeatureName, ...]],
    llm_choice: ReactorType | None,
    notes: list[str],
) -> _Hit:
    """按顺序试第二层的规则，取第一条命中的；沿途值得说明的原因写进 notes。"""
    for position, rule in enumerate(rules.priority, start=1):
        step = _APPLIERS[rule.rule](_Situation(features, buildable, lacking, llm_choice, rule))
        if step.picked is not None:
            hit_note = (step.note or "").format(name=REACTOR_NAMES[step.picked])
            notes.append(f"命中第二层第 {position} 条：{hit_note}")
            return _Hit(step.picked, position)
        if step.note:
            notes.append(step.note)
    notes.append(f"第二层的 {len(rules.priority)} 条都不满足，选 {REACTOR_NAMES[rules.fallback]}。")
    return _Hit(rules.fallback, len(rules.priority) + 1)


def check_rules(
    features: SelectionFeatures, rules: SelectionRules, llm_choice: ReactorType | None
) -> RuleVerdict:
    """从特征独立推出结论。llm_choice 只在 PFR 与 CSTR 之间定不下来时才用。"""
    if not features.is_reaction_process.value:
        return RuleVerdict(
            reactor_type=None,
            rule_number=None,
            buildable=(),
            unbuildable=(),
            notes=(NOT_A_REACTION_NOTE,),
        )
    buildable, lacking = _split_by_requirements(features, rules)
    notes = [_buildable_note(buildable, lacking)]
    hit = _walk_priority(features, rules, buildable, lacking, llm_choice, notes)
    if hit.reactor_type in SIZED_REACTORS and not features.dimensions_given.value:
        notes.append(MISSING_SIZE_NOTE)
    return RuleVerdict(
        reactor_type=hit.reactor_type,
        rule_number=hit.number,
        buildable=buildable,
        unbuildable=tuple(Unbuildable(reactor_type=k, missing=m) for k, m in lacking.items()),
        notes=tuple(notes),
    )


class Assessment(FrozenModel):
    """对一次 LLM 输出的评估：哪些依据不是原文，规则结论是什么，是否与推荐一致。"""

    invalid_evidence: tuple[str, ...]
    verdict: RuleVerdict
    agrees: bool

    @property
    def settled(self) -> bool:
        """一致并且依据都是原文，可以直接用，不必重问。"""
        return self.agrees and not self.invalid_evidence


def assess(draft: SelectionDraft, text: str, rules: SelectionRules) -> Assessment:
    """检查原文依据，做规则检查，与 LLM 的推荐对照。"""
    verdict = check_rules(draft.features, rules, draft.recommended_type)
    return Assessment(
        invalid_evidence=invalid_evidence(draft.features, text),
        verdict=verdict,
        agrees=verdict.reactor_type == draft.recommended_type,
    )


def _alternatives(verdict: RuleVerdict, draft: SelectionDraft) -> tuple[Alternative, ...]:
    """其余能建的类型各一条（LLM 的原因优先，没有就写优先级低），不能建的写缺什么。"""
    llm_reasons = {note.reactor_type: note.why_not for note in draft.alternatives}
    found = [
        (kind, True, llm_reasons.get(kind) or LOWER_PRIORITY_REASON)
        for kind in verdict.buildable
        if kind is not verdict.reactor_type
    ]
    found += [
        (item.reactor_type, False, f"缺少必要输入：{_missing_text(item.missing)}")
        for item in verdict.unbuildable
    ]
    return tuple(
        Alternative(
            reactor_type=kind,
            buildable=buildable,
            reason=(LLM_RECOMMENDED_PREFIX if kind is draft.recommended_type else "") + reason,
            recommended_by_llm=kind is draft.recommended_type,
        )
        for kind, buildable, reason in found
    )


def build_result(
    draft: SelectionDraft, text: str, assessment: Assessment, *, reasked: bool
) -> SelectionResult:
    """最终结果：类型取规则结论（一致时就是 LLM 的推荐），依据只留原文原话。"""
    verdict = assessment.verdict
    if not assessment.agrees:
        decision = Decision.RULES_PREVAILED
    else:
        decision = Decision.AGREED_AFTER_REASK if reasked else Decision.AGREED
    return SelectionResult(
        reactor_type=verdict.reactor_type,
        decision=decision,
        rule_notes=verdict.notes,
        llm_recommendation=draft.recommended_type,
        llm_rationale=draft.rationale,
        features=drop_invalid_evidence(draft.features, text),
        alternatives=_alternatives(verdict, draft),
        dropped_evidence=assessment.invalid_evidence,
    )


def _type_text(reactor_type: ReactorType | None) -> str:
    return (
        "不是反应过程（recommended_type 为 null）"
        if reactor_type is None
        else REACTOR_NAMES[reactor_type]
    )


def reask_feedback(draft: SelectionDraft, assessment: Assessment) -> str:
    """重问时告诉 LLM 要核对什么：与规则结论的分歧，以及在原文里找不到原话的依据。"""
    problems = []
    if not assessment.agrees:
        steps = "\n".join(f"   - {note}" for note in assessment.verdict.notes)
        problems.append(
            f"你推荐的是 {_type_text(draft.recommended_type)}，但按选择规则，由你抽取的特征推出的"
            f"结论是 {_type_text(assessment.verdict.reactor_type)}。规则的推导：\n{steps}"
        )
    if assessment.invalid_evidence:
        quoted = "；".join(f"“{text}”" for text in assessment.invalid_evidence)
        problems.append(
            f"这些依据在原文里找不到原话：{quoted}。依据必须逐字摘自原文；"
            "找不到原话支持的特征，请改成“否”。"
        )
    return "\n".join(f"{number}. {problem}" for number, problem in enumerate(problems, start=1))


def require_supported(result: SelectionResult, buildable: Collection[ReactorType]) -> None:
    """选型的结论系统做不做得了：不是反应过程，或者这种类型还不能建模，抛 E_UNSUPPORTED。"""
    if result.reactor_type is None:
        message = "这不是反应过程的模拟请求，系统只处理反应器的建模"
    elif result.reactor_type not in buildable:
        name = REACTOR_NAMES[result.reactor_type]
        message = f"选型的结论是 {name}，系统还不支持这种反应器的建模"
    else:
        return
    raise ReactorAgentError(ErrorCode.UNSUPPORTED, message)
