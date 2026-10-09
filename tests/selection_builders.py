"""选型测试共用的构造函数：特征、LLM 的输出、规则表。

规则表读的是 skills/reactor-selection/rules.yaml 本身，所以测试检查的就是真正在用的那张表。
"""

from pathlib import Path

from reactor_agent.spec.enums import ReactorType
from reactor_agent.spec.loading import parse_model, read_document
from reactor_agent.spec.selection import (
    AlternativeNote,
    EquipmentForm,
    FeatureName,
    FeedPhase,
    Flag,
    NamedReactor,
    SelectionDraft,
    SelectionFeatures,
    SelectionRules,
)

RULES_FILE = Path(__file__).resolve().parents[1] / "skills" / "reactor-selection" / "rules.yaml"
EVIDENCE_PREFIX = "原文"


def load_rules() -> SelectionRules:
    return parse_model(SelectionRules, read_document(RULES_FILE), RULES_FILE.name)


def make_features(
    *yes: FeatureName,
    named: ReactorType | None = None,
    form: EquipmentForm = EquipmentForm.UNSPECIFIED,
    phase: FeedPhase = FeedPhase.UNKNOWN,
    reaction_process: bool = True,
) -> SelectionFeatures:
    """列出取值为是的特征，其余都是否。依据是“原文<特征名>”，调用方需要时自己把它放进原文。"""
    wanted = set(yes)
    if reaction_process:
        wanted.add(FeatureName.IS_REACTION_PROCESS)

    def flag(name: FeatureName) -> Flag:
        present = name in wanted
        return Flag(value=present, evidence=f"{EVIDENCE_PREFIX}{name.value}" if present else None)

    return SelectionFeatures(
        is_reaction_process=flag(FeatureName.IS_REACTION_PROCESS),
        named_reactor=NamedReactor(
            reactor_type=named, evidence=None if named is None else f"{EVIDENCE_PREFIX}点名"
        ),
        kinetics_given=flag(FeatureName.KINETICS_GIVEN),
        dimensions_given=flag(FeatureName.DIMENSIONS_GIVEN),
        equipment_form=form,
        conversion_data_given=flag(FeatureName.CONVERSION_DATA_GIVEN),
        reaction_defined=flag(FeatureName.REACTION_DEFINED),
        black_box_system=flag(FeatureName.BLACK_BOX_SYSTEM),
        equilibrium_constant_given=flag(FeatureName.EQUILIBRIUM_CONSTANT_GIVEN),
        phase=phase,
        polymerization=flag(FeatureName.POLYMERIZATION),
    )


def cite(features: SelectionFeatures, text: str) -> SelectionFeatures:
    """把特征里所有的依据换成原文开头的一段，让依据检查通过。"""
    quote = text[:6]
    updates: dict[str, object] = {}
    for name in FeatureName:
        if features.flag(name).value:
            updates[name.value] = Flag(value=True, evidence=quote)
    named = features.named_reactor
    if named.reactor_type is not None:
        updates["named_reactor"] = NamedReactor(reactor_type=named.reactor_type, evidence=quote)
    return features.model_copy(update=updates)


def evidence_text(features: SelectionFeatures) -> str:
    """把 make_features 造出的全部依据拼成一段“原文”，让依据检查通过。"""
    return "，".join(quote.text for quote in features.quotes())


def make_draft(
    features: SelectionFeatures,
    recommended: ReactorType | None,
    why_not: dict[ReactorType, str] | None = None,
) -> SelectionDraft:
    return SelectionDraft(
        features=features,
        recommended_type=recommended,
        rationale="测试用的理由",
        alternatives=tuple(
            AlternativeNote(reactor_type=kind, why_not=reason)
            for kind, reason in (why_not or {}).items()
        ),
    )
