"""原文依据检查：全角半角、上下标、空白不同但内容相同的依据算通过，原文里没有的不通过。"""

import pytest
from pydantic import ValidationError

from reactor_agent.spec.enums import ReactorType
from reactor_agent.spec.selection import Flag, NamedReactor, SelectionDraft
from reactor_agent.spec.selection_rules import (
    drop_invalid_evidence,
    invalid_evidence,
    normalize_text,
)
from selection_builders import make_features

TEXT = "甲苯进料流量10000kg/h，进料温度为380℃，操作压力2.5MPa，发生歧化反应：2C₇H₈ → C₆H₆ + C₈H₁₀。"


def features_citing(evidence: str):
    base = make_features(reaction_process=False)
    return base.model_copy(update={"kinetics_given": Flag(value=True, evidence=evidence)})


@pytest.mark.parametrize(
    "evidence",
    [
        "甲苯进料流量10000kg/h",
        "甲苯 进料流量 10000 kg/h",  # 空白不同
        "进料温度为380°C",  # ℃ 与 °C
        "进料温度为380℃",
        "操作压力２．５ＭＰａ",  # 全角数字和字母
        "2C7H8 → C6H6 + C8H10",  # 上下标写成普通数字
        "2C₇H₈→C₆H₆+C₈H₁₀",
        "甲苯进料流量10000kg/h，\n进料温度为380℃",  # 换行
    ],
)
def test_evidence_that_differs_only_in_width_script_or_spaces_is_accepted(evidence):
    assert invalid_evidence(features_citing(evidence), TEXT) == ()


@pytest.mark.parametrize(
    "evidence",
    ["甲苯转化率为50%", "进料温度为400℃", "操作压力2.5MPa，温度380℃，", "…进料温度为380℃…"],
)
def test_evidence_that_is_not_in_the_text_is_rejected(evidence):
    assert invalid_evidence(features_citing(evidence), TEXT) == (evidence,)


def test_an_empty_or_blank_evidence_is_rejected():
    assert invalid_evidence(features_citing("  "), TEXT) == ("  ",)


def test_the_named_reactor_evidence_is_checked_too():
    features = make_features(reaction_process=False).model_copy(
        update={"named_reactor": NamedReactor(reactor_type=ReactorType.GIBBS, evidence="吉布斯")}
    )
    assert invalid_evidence(features, TEXT) == ("吉布斯",)
    assert invalid_evidence(features, TEXT + "吉布斯反应器") == ()


def test_features_that_are_no_have_no_evidence_to_check():
    assert invalid_evidence(make_features(reaction_process=False), TEXT) == ()


def test_dropping_removes_only_the_evidence_that_is_not_in_the_text():
    base = make_features()
    features = base.model_copy(
        update={
            "kinetics_given": Flag(value=True, evidence="进料温度为380℃"),
            "reaction_defined": Flag(value=True, evidence="原文里没有"),
        }
    )
    kept = drop_invalid_evidence(features, TEXT)
    assert kept.kinetics_given == Flag(value=True, evidence="进料温度为380℃")
    assert kept.reaction_defined == Flag(value=True, evidence=None)


def test_normalizing_is_idempotent_and_removes_all_whitespace():
    once = normalize_text("　甲苯\t 10000 ｋｇ/ｈ\n")
    assert once == "甲苯10000kg/h"
    assert normalize_text(once) == once


def draft_with(features):
    return {
        "features": features.model_dump(mode="json"),
        "recommended_type": "gibbs",
        "rationale": "理由",
        "alternatives": [],
    }


def test_a_draft_with_a_yes_feature_and_no_evidence_is_invalid():
    features = make_features().model_copy(
        update={"kinetics_given": Flag(value=True, evidence=None)}
    )
    with pytest.raises(ValidationError, match="给出了动力学参数"):
        SelectionDraft.model_validate(draft_with(features))


def test_a_draft_that_names_a_reactor_without_evidence_is_invalid():
    features = make_features().model_copy(
        update={"named_reactor": NamedReactor(reactor_type=ReactorType.PFR, evidence=None)}
    )
    with pytest.raises(ValidationError, match="用户点名的反应器"):
        SelectionDraft.model_validate(draft_with(features))


def test_a_draft_with_all_evidence_present_is_valid():
    SelectionDraft.model_validate(draft_with(make_features()))
