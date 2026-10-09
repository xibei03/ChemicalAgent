"""选型评测用例（evals/cases/）：格式、三个场景的原文逐字来自需求文档、不碰留出体系、每一类都有。"""

import re
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_DIR = REPO_ROOT / "evals" / "cases"
REQUIREMENT_FILE = REPO_ROOT / "docs" / "REQUIREMENT.md"

# 三个原文场景在需求文档里的行号（从 1 开始），只去掉行首的 > 和 **。
SCENARIO_LINES: Mapping[str, tuple[int, ...]] = {
    "L1-S1": (42, 43, 44, 45, 46),
    "L1-S2": (51, 52),
    "L1-S3": (57, 60),
}
SCENARIO_REPEATS = 5
REACTOR_VALUES = {"conversion", "equilibrium", "gibbs", "pfr", "cstr", "none"}
# 留出场景的体系（计划 §15.7）：评测用例和 Skill 都不能出现，要留到阶段 3A 检验泛化。
HELD_OUT_WORDS = ("乙醇", "合成氨", "氨合成", "燃烧")


def load_cases() -> dict[str, dict]:
    cases = {}
    for path in sorted(CASES_DIR.glob("*.yaml")):
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        case["_file"] = path.stem
        cases[case["id"]] = case
    return cases


CASES = load_cases()


def test_there_are_cases_and_ids_match_file_names():
    assert len(CASES) >= 20
    assert all(case["id"] == case["_file"] for case in CASES.values())


@pytest.mark.parametrize("case", CASES.values(), ids=list(CASES))
def test_every_case_has_the_fields_the_runner_needs(case):
    assert case["input"].strip() and case["purpose"].strip()
    assert case["expected"]["reactor"] in REACTOR_VALUES
    assert isinstance(case["expected"]["features"], dict) and case["expected"]["features"]


@pytest.mark.parametrize("case_id", SCENARIO_LINES)
def test_the_scenario_inputs_are_copied_verbatim_from_the_requirement_document(case_id):
    lines = REQUIREMENT_FILE.read_text(encoding="utf-8").split("\n")
    wanted = []
    for number in SCENARIO_LINES[case_id]:
        line = re.sub(r"^>\s*", "", lines[number - 1])
        wanted.append(re.sub(r"^\*\*", "", line))
    assert CASES[case_id]["input"] == "\n".join(wanted)


@pytest.mark.parametrize(("number", "case_id"), enumerate(SCENARIO_LINES, start=1))
def test_the_text_files_for_the_command_line_equal_the_scenario_cases(number, case_id):
    path = REPO_ROOT / "evals" / "inputs" / f"scenario-{number}.txt"
    assert path.read_text(encoding="utf-8").strip() == CASES[case_id]["input"]


@pytest.mark.parametrize("case_id", SCENARIO_LINES)
def test_the_scenarios_are_repeated_five_times_and_the_others_once(case_id):
    assert CASES[case_id]["repeats"] == SCENARIO_REPEATS
    others = [case for key, case in CASES.items() if key not in SCENARIO_LINES]
    assert all(case.get("repeats", 1) == 1 for case in others)


def test_the_scenario_expectations_are_the_ones_the_requirement_asks_for():
    assert CASES["L1-S1"]["expected"]["reactor"] == "equilibrium"
    assert CASES["L1-S2"]["expected"]["reactor"] == "conversion"
    assert CASES["L1-S3"]["expected"]["reactor"] == "gibbs"


def test_no_case_uses_a_held_out_system():
    hits = [
        f"{key}: {word}"
        for key, case in CASES.items()
        for word in HELD_OUT_WORDS
        if word in case["input"]
    ]
    assert not hits, f"评测用例不能用留出场景的体系：{hits}"


def test_every_kind_of_decision_in_the_selection_logic_has_a_case():
    by_reactor = {case["expected"]["reactor"] for case in CASES.values()}
    assert by_reactor == REACTOR_VALUES
    features = [case["expected"]["features"] for case in CASES.values()]

    def any_case(name: str, value: object) -> bool:
        return any(item.get(name) == value for item in features)

    assert any_case("polymerization", True)
    assert any_case("equilibrium_constant_given", True)
    assert any_case("is_reaction_process", False)
    assert any_case("equipment_form", "tubular") and any_case("equipment_form", "vessel")
    assert any_case("phase", "gas") and any_case("phase", "liquid")
    named = {item.get("named_reactor") for item in features} - {None}
    assert named == {"conversion", "equilibrium", "gibbs", "pfr", "cstr"}
