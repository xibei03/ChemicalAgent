"""反应器选型的数据模型：特征、LLM 的输出、规则表、选型结果。

一次 LLM 调用同时产出特征和推荐（SelectionDraft）；代码用规则表（SelectionRules）从特征独立推出
结论，和推荐对照，得到 SelectionResult。规则检查和原文依据检查是 selection_rules.py 里的纯函数。
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Self

from pydantic import Field, model_validator

from reactor_agent.spec.base import FrozenModel
from reactor_agent.spec.enums import ReactorType

REACTOR_NAMES: Mapping[ReactorType, str] = MappingProxyType(
    {
        ReactorType.CONVERSION: "Conversion",
        ReactorType.EQUILIBRIUM: "Equilibrium",
        ReactorType.GIBBS: "Gibbs",
        ReactorType.PFR: "PFR",
        ReactorType.CSTR: "CSTR",
    }
)


class EquipmentForm(StrEnum):
    """用户说明的反应器形式。"""

    TUBULAR = "tubular"
    VESSEL = "vessel"
    UNSPECIFIED = "unspecified"


class FeedPhase(StrEnum):
    """反应物的相态。"""

    GAS = "gas"
    LIQUID = "liquid"
    MULTIPHASE = "multiphase"
    UNKNOWN = "unknown"


class FeatureName(StrEnum):
    """取值是“是/否”的特征，名字就是 SelectionFeatures 里的字段名。规则表用它们表示必要输入。"""

    IS_REACTION_PROCESS = "is_reaction_process"
    KINETICS_GIVEN = "kinetics_given"
    DIMENSIONS_GIVEN = "dimensions_given"
    CONVERSION_DATA_GIVEN = "conversion_data_given"
    REACTION_DEFINED = "reaction_defined"
    BLACK_BOX_SYSTEM = "black_box_system"
    EQUILIBRIUM_CONSTANT_GIVEN = "equilibrium_constant_given"
    POLYMERIZATION = "polymerization"


FEATURE_LABELS: Mapping[FeatureName, str] = MappingProxyType(
    {
        FeatureName.IS_REACTION_PROCESS: "是反应过程的模拟请求",
        FeatureName.KINETICS_GIVEN: "给出了动力学参数",
        FeatureName.DIMENSIONS_GIVEN: "给出了设备尺寸",
        FeatureName.CONVERSION_DATA_GIVEN: "给出了转化率、收率或选择性的数值",
        FeatureName.REACTION_DEFINED: "反应已明确",
        FeatureName.BLACK_BOX_SYSTEM: "黑箱类体系",
        FeatureName.EQUILIBRIUM_CONSTANT_GIVEN: "给出了平衡常数",
        FeatureName.POLYMERIZATION: "聚合反应",
    }
)
NAMED_REACTOR_LABEL = "用户点名的反应器"


class Flag(FrozenModel):
    """一个“是/否”特征。取值为是时，evidence 是原文里的一句原话。"""

    value: bool
    evidence: str | None = None


class NamedReactor(FrozenModel):
    """用户点名的反应器类型，没有点名是 None；点名了要附原文里的原话。"""

    reactor_type: ReactorType | None
    evidence: str | None = None


class Quote(FrozenModel):
    """一条引用的原文依据，label 说明它支持哪个特征。"""

    label: str
    text: str


class SelectionFeatures(FrozenModel):
    """从原文抽取的特征，含义见 skills/reactor-selection/SKILL.md。字段的顺序就是模型填写的顺序。"""

    is_reaction_process: Flag
    named_reactor: NamedReactor
    kinetics_given: Flag
    dimensions_given: Flag
    equipment_form: EquipmentForm
    conversion_data_given: Flag
    reaction_defined: Flag
    black_box_system: Flag
    equilibrium_constant_given: Flag
    phase: FeedPhase
    polymerization: Flag

    def flag(self, name: FeatureName) -> Flag:
        """按特征名取“是/否”特征。"""
        flag: Flag = getattr(self, name.value)
        return flag

    def quotes(self) -> tuple[Quote, ...]:
        """全部引用了原文的依据：取值为是的特征，以及点名的反应器。"""
        found = [
            Quote(label=FEATURE_LABELS[name], text=flag.evidence)
            for name in FeatureName
            if (flag := self.flag(name)).value and flag.evidence
        ]
        if self.named_reactor.reactor_type is not None and self.named_reactor.evidence:
            found.append(Quote(label=NAMED_REACTOR_LABEL, text=self.named_reactor.evidence))
        return tuple(found)

    def missing_evidence(self) -> tuple[str, ...]:
        """应当带依据却没有带的特征，写成人读的名字。"""
        missing = [
            FEATURE_LABELS[name]
            for name in FeatureName
            if (flag := self.flag(name)).value and not (flag.evidence or "").strip()
        ]
        named = self.named_reactor
        if named.reactor_type is not None and not (named.evidence or "").strip():
            missing.append(NAMED_REACTOR_LABEL)
        return tuple(missing)


class AlternativeNote(FrozenModel):
    """LLM 给出的一条备选：这个类型为什么不选。"""

    reactor_type: ReactorType
    why_not: str


class SelectionDraft(FrozenModel):
    """一次选型调用 LLM 要交回的内容：特征、推荐的类型（不是反应过程时是 None）、理由、备选。"""

    features: SelectionFeatures
    recommended_type: ReactorType | None
    rationale: str = Field(min_length=1)
    alternatives: tuple[AlternativeNote, ...]

    @model_validator(mode="after")
    def _yes_features_carry_evidence(self) -> Self:
        missing = self.features.missing_evidence()
        if missing:
            raise ValueError(
                f"取值为是的特征和点名的反应器必须附原文依据，缺少：{'、'.join(missing)}"
            )
        return self


class PriorityRuleId(StrEnum):
    """第二层规则的名字。每一条的判断逻辑在 selection_rules.py 里，规则表只决定顺序。"""

    NAMED_REACTOR = "named_reactor"
    KINETIC = "kinetic"
    CONVERSION = "conversion"
    BLACK_BOX = "black_box"
    EQUILIBRIUM = "equilibrium"


class PriorityRule(FrozenModel):
    """第二层的一条规则：候选类型，以及（可选）必须为“是”的另一个特征。"""

    rule: PriorityRuleId
    candidates: tuple[ReactorType, ...] = ()
    when: FeatureName | None = None


class SelectionRules(FrozenModel):
    """规则表（skills/reactor-selection/rules.yaml）。

    requirements: 每种类型“能建”所需的特征，都必须为是。
    priority: 第二层，在能建的类型里按这个顺序取第一条命中的。
    fallback: 第二层都不命中时选的类型，它必须随时能建。
    """

    requirements: Mapping[ReactorType, tuple[FeatureName, ...]]
    priority: tuple[PriorityRule, ...]
    fallback: ReactorType

    @model_validator(mode="after")
    def _table_is_complete(self) -> Self:
        missing = [kind.value for kind in ReactorType if kind not in self.requirements]
        if missing:
            raise ValueError(f"requirements 缺少这些类型：{'、'.join(missing)}")
        if self.requirements[self.fallback]:
            raise ValueError("fallback 的必要输入必须为空，否则第二层可能没有结论")
        return self


class Decision(StrEnum):
    """最终类型是怎么定的。"""

    AGREED = "agreed"
    AGREED_AFTER_REASK = "agreed_after_reask"
    RULES_PREVAILED = "rules_prevailed"


class Unbuildable(FrozenModel):
    """一个不能建的类型和它缺的特征。"""

    reactor_type: ReactorType
    missing: tuple[FeatureName, ...]


class RuleVerdict(FrozenModel):
    """规则这一侧的结论。reactor_type 是 None 表示不是反应过程，没有可选的类型。

    rule_number 是命中第二层的第几条（从 1 起；都不命中而取 fallback 时是表的长度加 1）。
    """

    reactor_type: ReactorType | None
    rule_number: int | None
    buildable: tuple[ReactorType, ...]
    unbuildable: tuple[Unbuildable, ...]
    notes: tuple[str, ...]


class Alternative(FrozenModel):
    """一个没有选的类型：能不能建，以及不选的原因。"""

    reactor_type: ReactorType
    buildable: bool
    reason: str
    recommended_by_llm: bool = False


class SelectionSummary(FrozenModel):
    """状态文件里存的摘要：类型和它是怎么定的。完整的结果在 artifacts/selection.json。"""

    reactor_type: ReactorType | None
    decision: Decision


class SelectionResult(FrozenModel):
    """选型的最终结果。rule_notes 由代码生成，所以 LLM 的推荐被推翻时，理由也和结论对得上。"""

    reactor_type: ReactorType | None
    decision: Decision
    rule_notes: tuple[str, ...]
    llm_recommendation: ReactorType | None
    llm_rationale: str
    features: SelectionFeatures
    alternatives: tuple[Alternative, ...]

    @property
    def summary(self) -> SelectionSummary:
        """状态文件里存的那部分。"""
        return SelectionSummary(reactor_type=self.reactor_type, decision=self.decision)
