"""选型的规则检查：第一层能不能建，第二层的每一条，PFR 与 CSTR 之间的选择，聚合反应的例外，对照。

规则表读 skills/reactor-selection/rules.yaml，所以测的是真正在用的那一张。
"""

import pytest
from pydantic import ValidationError

from reactor_agent.spec.enums import ReactorType
from reactor_agent.spec.selection import (
    REACTOR_NAMES,
    Decision,
    EquipmentForm,
    FeedPhase,
    PriorityRuleId,
    SelectionRules,
)
from reactor_agent.spec.selection import FeatureName as F
from reactor_agent.spec.selection_rules import (
    LOWER_PRIORITY_REASON,
    MISSING_SIZE_NOTE,
    POLYMER_EXCEPTION_NOTE,
    assess,
    build_result,
    check_rules,
)
from selection_builders import evidence_text, load_rules, make_draft, make_features

RULES = load_rules()
CONVERSION, EQUILIBRIUM, GIBBS = ReactorType.CONVERSION, ReactorType.EQUILIBRIUM, ReactorType.GIBBS
PFR, CSTR = ReactorType.PFR, ReactorType.CSTR


def verdict_of(*yes, llm=None, **kwargs):
    return check_rules(make_features(*yes, **kwargs), RULES, llm)


def text_of(verdict) -> str:
    return "\n".join(verdict.notes)


# ---------- 规则表本身 ----------


def test_the_rules_table_lists_the_five_types_and_the_requirement_order():
    assert set(RULES.requirements) == set(ReactorType)
    assert [rule.rule for rule in RULES.priority] == list(PriorityRuleId)
    assert RULES.fallback is GIBBS and RULES.requirements[GIBBS] == ()


def test_a_table_without_a_type_is_refused():
    broken = RULES.model_dump(mode="json")
    del broken["requirements"]["cstr"]
    with pytest.raises(ValidationError, match="cstr"):
        SelectionRules.model_validate(broken)


def test_a_fallback_that_needs_inputs_is_refused():
    broken = RULES.model_dump(mode="json")
    broken["fallback"] = "pfr"
    with pytest.raises(ValidationError, match="fallback"):
        SelectionRules.model_validate(broken)


# ---------- 第一层：能不能建 ----------


def test_gibbs_can_always_be_built_and_the_others_need_their_inputs():
    verdict = verdict_of()
    assert verdict.buildable == (GIBBS,)
    assert {item.reactor_type for item in verdict.unbuildable} == {
        CONVERSION,
        EQUILIBRIUM,
        PFR,
        CSTR,
    }


@pytest.mark.parametrize(
    ("feature", "unlocked"),
    [
        (F.CONVERSION_DATA_GIVEN, {CONVERSION}),
        (F.REACTION_DEFINED, {EQUILIBRIUM}),
        (F.KINETICS_GIVEN, {PFR, CSTR}),
    ],
)
def test_each_type_becomes_buildable_when_its_required_feature_is_yes(feature, unlocked):
    verdict = verdict_of(feature)
    assert set(verdict.buildable) == {GIBBS} | unlocked


def test_the_notes_say_which_types_cannot_be_built_and_what_they_lack():
    note = verdict_of().notes[0]
    assert "能建的类型：Gibbs" in note
    assert "Conversion（缺：给出了转化率、收率或选择性的数值）" in note
    assert "PFR（缺：给出了动力学参数）" in note


def test_an_equilibrium_constant_is_not_required_for_the_equilibrium_reactor():
    assert verdict_of(F.REACTION_DEFINED).reactor_type is EQUILIBRIUM


# ---------- 第二层第 1 条：用户点名 ----------


@pytest.mark.parametrize(
    ("named", "inputs"),
    [
        (CONVERSION, [F.CONVERSION_DATA_GIVEN]),
        (EQUILIBRIUM, [F.REACTION_DEFINED]),
        (GIBBS, []),
        (PFR, [F.KINETICS_GIVEN]),
        (CSTR, [F.KINETICS_GIVEN, F.CONVERSION_DATA_GIVEN, F.REACTION_DEFINED]),
    ],
)
def test_a_named_type_with_its_required_inputs_is_taken_before_anything_else(named, inputs):
    verdict = verdict_of(*inputs, named=named, phase=FeedPhase.GAS)
    assert verdict.reactor_type is named and verdict.rule_number == 1
    assert f"用户点名了 {REACTOR_NAMES[named]}" in text_of(verdict)


def test_a_named_gibbs_beats_a_fully_defined_reaction():
    verdict = verdict_of(F.REACTION_DEFINED, named=GIBBS)
    assert verdict.reactor_type is GIBBS and verdict.rule_number == 1


def test_a_named_type_lacking_inputs_is_explained_and_the_rules_go_on():
    verdict = verdict_of(F.CONVERSION_DATA_GIVEN, named=PFR)
    assert verdict.reactor_type is CONVERSION and verdict.rule_number == 3
    assert "用户点名了 PFR，但缺少：给出了动力学参数，不采纳，继续往下判断" in text_of(verdict)


def test_a_named_equilibrium_without_a_defined_reaction_falls_to_gibbs():
    verdict = verdict_of(named=EQUILIBRIUM)
    assert verdict.reactor_type is GIBBS
    assert "用户点名了 Equilibrium，但缺少：反应已明确" in text_of(verdict)


# ---------- 第二层第 2 条：动力学反应器 ----------


@pytest.mark.parametrize(
    ("form", "phase", "expected"),
    [
        (EquipmentForm.TUBULAR, FeedPhase.UNKNOWN, PFR),
        (EquipmentForm.VESSEL, FeedPhase.UNKNOWN, CSTR),
        (EquipmentForm.TUBULAR, FeedPhase.LIQUID, PFR),
        (EquipmentForm.VESSEL, FeedPhase.GAS, CSTR),
        (EquipmentForm.UNSPECIFIED, FeedPhase.GAS, PFR),
        (EquipmentForm.UNSPECIFIED, FeedPhase.LIQUID, CSTR),
    ],
)
def test_form_decides_between_pfr_and_cstr_then_phase(form, phase, expected):
    verdict = verdict_of(F.KINETICS_GIVEN, form=form, phase=phase)
    assert verdict.reactor_type is expected and verdict.rule_number == 2


@pytest.mark.parametrize("phase", [FeedPhase.MULTIPHASE, FeedPhase.UNKNOWN])
@pytest.mark.parametrize("llm_choice", [PFR, CSTR])
def test_when_neither_form_nor_phase_decides_the_llm_recommendation_is_used(phase, llm_choice):
    verdict = verdict_of(F.KINETICS_GIVEN, phase=phase, llm=llm_choice)
    assert verdict.reactor_type is llm_choice
    assert "采用 LLM 的推荐" in text_of(verdict)


def test_when_nothing_decides_and_the_llm_chose_another_type_the_first_candidate_is_taken():
    verdict = verdict_of(F.KINETICS_GIVEN, llm=GIBBS)
    assert verdict.reactor_type is PFR


def test_kinetics_beat_conversion_data_and_a_defined_reaction():
    verdict = verdict_of(
        F.KINETICS_GIVEN, F.CONVERSION_DATA_GIVEN, F.REACTION_DEFINED, phase=FeedPhase.LIQUID
    )
    assert verdict.reactor_type is CSTR


def test_a_missing_size_is_pointed_out_for_kinetic_reactors_only():
    assert MISSING_SIZE_NOTE in text_of(verdict_of(F.KINETICS_GIVEN, phase=FeedPhase.GAS))
    sized = verdict_of(F.KINETICS_GIVEN, F.DIMENSIONS_GIVEN, phase=FeedPhase.GAS)
    assert MISSING_SIZE_NOTE not in text_of(sized)
    assert MISSING_SIZE_NOTE not in text_of(verdict_of(F.CONVERSION_DATA_GIVEN))


def test_a_tubular_or_vessel_form_without_kinetics_does_not_make_a_kinetic_reactor():
    verdict = verdict_of(F.REACTION_DEFINED, F.DIMENSIONS_GIVEN, form=EquipmentForm.TUBULAR)
    assert verdict.reactor_type is EQUILIBRIUM


# ---------- 聚合反应的例外 ----------


def test_polymerization_skips_the_kinetic_rule_and_says_it_is_the_exception():
    verdict = verdict_of(F.KINETICS_GIVEN, F.POLYMERIZATION, F.CONVERSION_DATA_GIVEN)
    assert verdict.reactor_type is CONVERSION and verdict.rule_number == 3
    assert POLYMER_EXCEPTION_NOTE in text_of(verdict)


def test_polymerization_with_kinetics_but_nothing_else_goes_on_to_the_later_rules():
    verdict = verdict_of(F.KINETICS_GIVEN, F.POLYMERIZATION, F.REACTION_DEFINED)
    assert verdict.reactor_type is EQUILIBRIUM
    fallback = verdict_of(F.KINETICS_GIVEN, F.POLYMERIZATION)
    assert fallback.reactor_type is GIBBS and fallback.rule_number == 6


def test_polymerization_without_kinetics_has_no_exception_to_mention():
    assert POLYMER_EXCEPTION_NOTE not in text_of(verdict_of(F.POLYMERIZATION, F.REACTION_DEFINED))


def test_a_named_kinetic_reactor_is_still_taken_for_a_polymerization():
    verdict = verdict_of(F.KINETICS_GIVEN, F.POLYMERIZATION, named=CSTR)
    assert verdict.reactor_type is CSTR and verdict.rule_number == 1


# ---------- 第二层第 3 至 6 条 ----------


def test_conversion_data_beat_a_defined_reaction():
    verdict = verdict_of(F.CONVERSION_DATA_GIVEN, F.REACTION_DEFINED)
    assert verdict.reactor_type is CONVERSION and verdict.rule_number == 3


def test_conversion_data_beat_the_black_box_rule():
    assert verdict_of(F.CONVERSION_DATA_GIVEN, F.BLACK_BOX_SYSTEM).reactor_type is CONVERSION


def test_a_black_box_system_gets_gibbs_even_when_a_reaction_is_written_out():
    verdict = verdict_of(F.BLACK_BOX_SYSTEM, F.REACTION_DEFINED)
    assert verdict.reactor_type is GIBBS and verdict.rule_number == 4
    assert EQUILIBRIUM in verdict.buildable


def test_a_defined_reaction_gets_equilibrium_whether_or_not_k_is_given():
    plain = verdict_of(F.REACTION_DEFINED)
    with_k = verdict_of(F.REACTION_DEFINED, F.EQUILIBRIUM_CONSTANT_GIVEN)
    assert plain.reactor_type is with_k.reactor_type is EQUILIBRIUM
    assert plain.rule_number == with_k.rule_number == 5


def test_when_nothing_applies_the_answer_is_gibbs_and_the_notes_say_so():
    verdict = verdict_of()
    assert verdict.reactor_type is GIBBS and verdict.rule_number == 6
    assert "第二层的 5 条都不满足，选 Gibbs" in text_of(verdict)


def test_a_request_that_is_not_a_reaction_process_has_no_reactor():
    verdict = verdict_of(F.KINETICS_GIVEN, F.REACTION_DEFINED, reaction_process=False)
    assert verdict.reactor_type is None and verdict.rule_number is None
    assert verdict.buildable == () and verdict.unbuildable == ()
    assert "不是反应过程" in text_of(verdict)


def test_the_llm_recommendation_does_not_change_a_decided_rule_conclusion():
    for llm in (None, GIBBS, PFR, CSTR):
        assert verdict_of(F.REACTION_DEFINED, llm=llm).reactor_type is EQUILIBRIUM


# ---------- 对照与最终结果 ----------


def settle(features, recommended, why_not=None, *, reasked=False):
    draft = make_draft(features, recommended, why_not)
    text = evidence_text(features)
    assessment = assess(draft, text, RULES)
    return assessment, build_result(draft, text, assessment, reasked=reasked)


def test_agreement_with_valid_evidence_is_settled_and_the_decision_is_agreed():
    assessment, result = settle(make_features(F.REACTION_DEFINED), EQUILIBRIUM)
    assert assessment.settled and assessment.agrees
    assert result.reactor_type is EQUILIBRIUM and result.decision is Decision.AGREED


def test_agreement_after_a_second_ask_is_recorded_as_such():
    _, result = settle(make_features(F.REACTION_DEFINED), EQUILIBRIUM, reasked=True)
    assert result.decision is Decision.AGREED_AFTER_REASK


def test_a_disagreement_is_not_settled_and_the_rule_conclusion_wins():
    assessment, result = settle(make_features(F.REACTION_DEFINED), GIBBS)
    assert not assessment.agrees and not assessment.settled
    assert result.reactor_type is EQUILIBRIUM and result.decision is Decision.RULES_PREVAILED
    assert result.llm_recommendation is GIBBS and result.llm_rationale


def test_agreeing_on_a_request_that_is_not_a_reaction_is_a_valid_agreement():
    assessment, result = settle(make_features(reaction_process=False), None)
    assert assessment.settled and result.reactor_type is None
    assert result.alternatives == ()


def test_the_llm_naming_a_type_for_a_non_reaction_request_is_a_disagreement():
    assessment, _ = settle(make_features(reaction_process=False), GIBBS)
    assert not assessment.agrees


def test_evidence_that_is_not_in_the_text_makes_the_answer_unsettled_even_when_types_agree():
    features = make_features(F.REACTION_DEFINED)
    draft = make_draft(features, EQUILIBRIUM)
    assessment = assess(draft, "原文里没有那句话", RULES)
    assert assessment.agrees and not assessment.settled
    assert set(assessment.invalid_evidence) == {"原文reaction_defined", "原文is_reaction_process"}


def test_invalid_evidence_is_dropped_from_the_final_result_but_the_feature_value_stays():
    features = make_features(F.REACTION_DEFINED)
    draft = make_draft(features, EQUILIBRIUM)
    result = build_result(draft, "没有依据", assess(draft, "没有依据", RULES), reasked=True)
    assert result.features.reaction_defined.value is True
    assert result.features.reaction_defined.evidence is None
    assert result.features.quotes() == ()


def test_alternatives_use_the_llm_reason_then_the_default_and_say_what_is_missing():
    features = make_features(F.CONVERSION_DATA_GIVEN, F.REACTION_DEFINED)
    _, result = settle(features, CONVERSION, {EQUILIBRIUM: "平衡由用户给定的转化率代替"})
    by_type = {item.reactor_type: item for item in result.alternatives}
    assert set(by_type) == {EQUILIBRIUM, GIBBS, PFR, CSTR}
    assert (
        by_type[EQUILIBRIUM].buildable
        and by_type[EQUILIBRIUM].reason == "平衡由用户给定的转化率代替"
    )
    assert by_type[GIBBS].buildable and by_type[GIBBS].reason == LOWER_PRIORITY_REASON
    assert not by_type[PFR].buildable and "缺少必要输入：给出了动力学参数" in by_type[PFR].reason


def test_an_overridden_llm_recommendation_is_listed_as_an_alternative():
    _, result = settle(make_features(F.REACTION_DEFINED), GIBBS)
    gibbs = next(item for item in result.alternatives if item.reactor_type is GIBBS)
    assert gibbs.recommended_by_llm and gibbs.reason == LOWER_PRIORITY_REASON
    assert all(not item.recommended_by_llm for item in result.alternatives if item is not gibbs)


def test_the_chosen_type_is_never_listed_among_its_own_alternatives():
    _, result = settle(make_features(F.REACTION_DEFINED), EQUILIBRIUM)
    assert EQUILIBRIUM not in {item.reactor_type for item in result.alternatives}


def test_the_summary_keeps_only_the_type_and_how_it_was_decided():
    _, result = settle(make_features(F.REACTION_DEFINED), GIBBS)
    assert result.summary.reactor_type is EQUILIBRIUM
    assert result.summary.decision is Decision.RULES_PREVAILED
