"""Skill 的内容：不泄题（场景原文、场景体系、留出体系），示例自洽，特征的定义没有和模型脱节。

“不泄题”对 skills/ 下所有的 Skill 都生效，包括后面阶段新增的。检查得出照抄，查不出改写和
单个数值，后两者靠写 Skill 的人自己把关。
"""

import json
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path

import pytest
import yaml

from reactor_agent.skill_loader import list_files, load_rules, load_skill, read_file
from reactor_agent.spec.enums import ReactorType, WorkflowState
from reactor_agent.spec.selection import SelectionDraft, SelectionFeatures, SelectionRules
from reactor_agent.spec.selection_rules import assess, invalid_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"
CASES_DIR = REPO_ROOT / "evals" / "cases"
SCENARIO_IDS = ("L1-S1", "L1-S2", "L1-S3")
WINDOW = 12
# 对全部评测用例的检查只看汉字够多的片段，免得“压力3bar。请”这类通用说法造成误报。
MIN_CJK_IN_BROAD_WINDOW = 8
CJK = re.compile(r"[一-鿿]")
# 三个考核场景的体系，以及留出场景的体系（计划 §15.7）。Skill 写一般性的判断标准，不点体系的名。
SCENARIO_SYSTEMS = ("重整", "歧化", "水煤浆", "煤炭", "甲烷", "甲苯")
HELD_OUT_SYSTEMS = ("乙醇", "合成氨", "氨合成", "甲烷与空气")
SELECTION = "reactor-selection"


def squash(text: str) -> str:
    """NFKC 规范化并去掉全部空白，比较前两边都这样处理。"""
    return "".join(unicodedata.normalize("NFKC", text).split())


def windows(text: str, min_cjk: int = 0) -> set[str]:
    flat = squash(text)
    pieces = {flat[start : start + WINDOW] for start in range(len(flat) - WINDOW + 1)}
    return {piece for piece in pieces if len(CJK.findall(piece)) >= min_cjk}


def case_inputs(ids: Iterable[str] | None = None) -> dict[str, str]:
    found = {}
    for path in sorted(CASES_DIR.glob("*.yaml")):
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        if ids is None or case["id"] in ids:
            found[case["id"]] = case["input"]
    return found


def skill_files() -> list[Path]:
    return sorted(path for path in SKILLS_DIR.rglob("*") if path.is_file())


def copied_fragments(files: Iterable[Path], texts: Iterable[str], min_cjk: int = 0) -> list[str]:
    """Skill 文件里出现的、与这些文本相同的连续 12 个字符，写成“文件：片段”。"""
    fragments: set[str] = set()
    for text in texts:
        fragments |= windows(text, min_cjk)
    found = []
    for path in files:
        flat = squash(path.read_text(encoding="utf-8"))
        found += [
            f"{path.parent.name}/{path.name}：{piece}"
            for piece in sorted(fragments)
            if piece in flat
        ]
    return found


def test_the_skills_directory_has_files_to_check():
    assert len(skill_files()) >= 6 and len(case_inputs(SCENARIO_IDS)) == len(SCENARIO_IDS)


def test_no_skill_file_contains_twelve_consecutive_characters_of_a_scenario_input():
    leaked = copied_fragments(skill_files(), case_inputs(SCENARIO_IDS).values())
    assert not leaked, f"Skill 里有场景原文的片段：{leaked[:5]}"


def test_no_skill_file_copies_the_eval_cases_either():
    leaked = copied_fragments(skill_files(), case_inputs().values(), MIN_CJK_IN_BROAD_WINDOW)
    assert not leaked, f"Skill 里有评测用例的片段（示例不能和评测用例用同一个体系）：{leaked[:5]}"


def test_the_copy_detector_does_catch_a_copied_sentence(tmp_path):
    scenario = next(iter(case_inputs(["L1-S2"]).values()))
    sentence = scenario[10:40]
    leaky = tmp_path / "leaky.md"
    leaky.write_text(f"前面的话 {sentence} 后面的话", encoding="utf-8")
    assert copied_fragments([leaky], [scenario])
    clean = tmp_path / "clean.md"
    clean.write_text("一段完全无关的文字，讲的是别的东西，没有任何重合的内容。", encoding="utf-8")
    assert not copied_fragments([clean], [scenario])


@pytest.mark.parametrize("word", SCENARIO_SYSTEMS + HELD_OUT_SYSTEMS)
def test_skills_do_not_name_the_scenario_or_held_out_systems(word):
    hits = [
        path.relative_to(SKILLS_DIR).as_posix()
        for path in skill_files()
        if word in path.read_text(encoding="utf-8")
    ]
    assert not hits, f"{hits} 里出现了“{word}”：Skill 写判断标准和一般性的工艺知识，不点体系的名"


def test_the_selection_skill_loads_with_its_references_examples_and_rules():
    skill = load_skill(SKILLS_DIR, SELECTION)
    assert skill.used_in == (WorkflowState.SELECT,) and skill.version
    assert list_files(skill, "references") == ("pitfalls.md", "selection_rules.md")
    assert len(list_files(skill, "examples")) >= 2
    assert isinstance(load_rules(skill, SelectionRules), SelectionRules)


def test_the_skill_defines_every_feature_the_model_extracts():
    body = load_skill(SKILLS_DIR, SELECTION).body
    missing = [name for name in SelectionFeatures.model_fields if f"`{name}`" not in body]
    assert not missing, f"SKILL.md 没有定义这些特征：{missing}"


def test_the_skill_names_all_five_types_and_the_rule_exceptions():
    skill = load_skill(SKILLS_DIR, SELECTION)
    text = skill.body + read_file(skill, "references", "selection_rules.md")
    for kind in ReactorType:
        assert f"`{kind.value}`" in text or kind.value.capitalize() in text or kind.name in text
    assert "聚合反应不适用" in text


def example_parts(path: Path) -> tuple[str, SelectionDraft]:
    text = path.read_text(encoding="utf-8")
    source = re.search(r"## 输入\s+(.*?)\s+## 输出", text, re.DOTALL)
    output = re.search(r"```json\s+(.*?)\s+```", text, re.DOTALL)
    assert source and output, f"{path.name} 的格式不对"
    return source.group(1), SelectionDraft.model_validate(json.loads(output.group(1)))


EXAMPLES = sorted((SKILLS_DIR / SELECTION / "examples").glob("*.md"))


@pytest.mark.parametrize("path", EXAMPLES, ids=[path.stem for path in EXAMPLES])
def test_every_example_is_valid_and_its_evidence_is_quoted_from_its_own_input(path):
    text, draft = example_parts(path)
    assert invalid_evidence(draft.features, text) == ()


@pytest.mark.parametrize("path", EXAMPLES, ids=[path.stem for path in EXAMPLES])
def test_the_rules_reach_the_same_type_as_every_example(path):
    text, draft = example_parts(path)
    rules = load_rules(load_skill(SKILLS_DIR, SELECTION), SelectionRules)
    assessment = assess(draft, text, rules)
    assert assessment.settled, assessment.verdict.notes


@pytest.mark.parametrize("path", EXAMPLES, ids=[path.stem for path in EXAMPLES])
def test_an_example_gives_a_reason_for_every_other_type_unless_it_is_not_a_reaction(path):
    _, draft = example_parts(path)
    if draft.recommended_type is None:
        assert draft.alternatives == ()
        return
    listed = {note.reactor_type for note in draft.alternatives}
    assert listed == set(ReactorType) - {draft.recommended_type}
