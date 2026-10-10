"""运行评测：每个用例跑真实的选型，有期望参数或期望问题的接着写规格、校验、编译计划。

和 `run --dry-run` 同一条路径，不碰 HYSYS；打分，写评测结果文件。

三个原文场景各重复 5 次，其余用例各 1 次（次数写在用例文件里）。
  python evals/run_evals.py [--cases L1-S1,L1-K1] [--output 结果文件] [--repeats N]
需要 LLM 密钥，只从环境变量读（名字在 config/settings.yaml）。没有设置环境变量时，用
`python evals/interactive.py` 在终端里输入一次密钥，再从菜单运行评测。
每次运行的目录在 runs/evals-<时间>/ 下，有 LLM 的提示和回复全文。
默认：跑全部用例写 docs/EVAL_RESULTS.md；只跑部分用例写在运行目录里，不覆盖完整的结果。
退出码：选型和规格两个门槛都通过是 0，没通过是 1，没有密钥是 2。
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from scoring import EvalCase, RunRecord, load_cases, render_report, summarize
from spec_report import render_spec_report, spec_gate
from spec_scoring import STOPPED, IssueKey, SpecRecord

from reactor_agent.cli import (
    REPO_ROOT,
    SETTINGS_FILE,
    SKILLS_DIR,
    build_text_run,
    create_llm_client,
)
from reactor_agent.errors import ReactorAgentError
from reactor_agent.harness.selection import SELECTION_SKILL
from reactor_agent.llm.client import LlmClient
from reactor_agent.observability.trace import TRACE_FILE, read_events
from reactor_agent.skill_loader import Skill, load_rules, load_skill
from reactor_agent.spec.enums import WorkflowState
from reactor_agent.spec.llm import LlmCallRecord
from reactor_agent.spec.model_spec import ModelSpec
from reactor_agent.spec.selection import SelectionDraft, SelectionResult, SelectionRules
from reactor_agent.spec.selection_rules import check_rules
from reactor_agent.spec.settings import LlmSettings, load_settings
from reactor_agent.state.models import TaskState
from reactor_agent.state.store import ArtifactName, StateStore

CASES_DIR = REPO_ROOT / "evals" / "cases"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "EVAL_RESULTS.md"
EXIT_NO_KEY = 2


def read_logs(run_dir: Path, point: str = "select") -> list[LlmCallRecord]:
    """这次运行里某个调用点按顺序的全部 LLM 调用记录（select-1、select-2……）。"""
    files = (run_dir / "llm").glob(f"{point}-*.json")
    ordered = sorted(files, key=lambda p: int(p.stem.split("-")[1]))
    return [LlmCallRecord.model_validate_json(f.read_text(encoding="utf-8")) for f in ordered]


def spec_record_of(task: TaskState, store: StateStore) -> SpecRecord:
    """规格这一步的结果：冻结出的规格、重写轮数、第一次校验的问题、最终的原因。"""
    spec = None
    if store.artifact_path(task.task_id, ArtifactName.MODEL_SPEC).is_file():
        spec = store.read_artifact(task.task_id, ArtifactName.MODEL_SPEC, ModelSpec)
    events = read_events(store.run_dir(task.task_id) / TRACE_FILE)
    first = next((e for e in events if e.name == "spec_issues"), None)
    listed = first.output.get("issues", []) if first and isinstance(first.output, dict) else []
    issues = tuple(
        IssueKey(code=item["code"], field_path=item["field_path"])
        for item in listed
        if isinstance(item, dict)
    )
    stopped = task.status in STOPPED and bool(task.errors)
    paths = tuple(task.errors[-1].details) if stopped else ()
    return SpecRecord(
        status=task.status,
        spec=spec,
        rewrites=task.spec_rewrites,
        first_issues=issues,
        final_paths=paths,
    )


def first_answer(logs: list[LlmCallRecord]) -> SelectionDraft | None:
    """第一次调用拿到的、通过了校验的回答。第一次调用就没有拿到合法的输出时是 None。"""
    if not logs or logs[0].attempts[-1].validation_error is not None:
        return None
    return SelectionDraft.model_validate_json(logs[0].attempts[-1].reply_text)


def record_of(
    case: EvalCase, repeat: int, task: TaskState, store: StateStore, rules: SelectionRules
) -> RunRecord:
    """从运行目录里收集打分需要的东西。"""
    saved = store.artifact_path(task.task_id, ArtifactName.SELECTION)
    selection = None
    if saved.is_file():
        selection = store.read_artifact(task.task_id, ArtifactName.SELECTION, SelectionResult)
    logs = read_logs(store.run_dir(task.task_id))
    spec_logs = read_logs(store.run_dir(task.task_id), "specify")
    first = first_answer(logs)
    return RunRecord(
        case_id=case.id,
        repeat=repeat,
        selection=selection,
        first_recommendation=first.recommended_type if first else None,
        first_rule_type=check_rules(first.features, rules, first.recommended_type).reactor_type
        if first
        else None,
        has_first_answer=first is not None,
        error=task.errors[-1].message if task.errors else None,
        tokens=sum(log.total_tokens for log in [*logs, *spec_logs]),
        seconds=0.0,
        reasked=len(logs) > 1,
        spec=spec_record_of(task, store) if case.runs_spec else None,
    )


def run_one(
    llm: LlmClient, case: EvalCase, repeat: int, runs_dir: Path, rules: SelectionRules
) -> RunRecord:
    """跑一次选型（有期望参数或期望问题的用例接着写规格），返回打分需要的记录。"""
    run = build_text_run(llm, runs_dir)
    started = time.monotonic()
    task = run.selector.create_task(case.input)
    stop_at = WorkflowState.PREFLIGHT if case.runs_spec else WorkflowState.SPECIFY
    run.engine.run(task, stop_at=stop_at)
    seconds = time.monotonic() - started
    return record_of(case, repeat, task, run.store, rules).model_copy(update={"seconds": seconds})


def _spec_tail(record: RunRecord) -> str:
    """进度行里规格这一步的结果。"""
    spec = record.spec
    if spec is None:
        return ""
    state = (
        "规格合法"
        if spec.spec is not None
        else f"终态 {spec.status.value if spec.status else '无'}"
    )
    return f"，{state}，重写 {spec.rewrites} 轮"


def run_all(
    llm: LlmClient, cases: list[EvalCase], runs_dir: Path, rules: SelectionRules
) -> list[RunRecord]:
    """按顺序跑全部用例的全部重复，边跑边打印进度。"""
    records = []
    for case in cases:
        for repeat in range(1, case.repeats + 1):
            record = run_one(llm, case, repeat, runs_dir, rules)
            records.append(record)
            mark = "✓" if record.selection and record.final_type == case.expected.reactor else "✗"
            where = f"第 {repeat}/{case.repeats} 次"
            print(
                f"{mark} {case.id} {where}：{record.final_type}{_spec_tail(record)}"
                f"（{record.seconds:.1f} 秒）",
                flush=True,
            )
    return records


def git_state() -> str:
    """提交哈希，工作区有未提交改动时注明。"""

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8"
        )
        return done.stdout.strip()

    dirty = "，有未提交的改动" if git("status", "--porcelain") else ""
    return f"{git('rev-parse', '--short', 'HEAD')}{dirty}"


def metadata(settings: LlmSettings, skill: Skill, runs_dir: Path) -> dict[str, str]:
    """写进结果文件开头的信息：模型、Skill 的版本和哈希、提交、时间、运行目录。"""
    return {
        "模型": settings.model,
        "Skill": f"{skill.name} {skill.version}（内容哈希 {skill.content_hash[:12]}）",
        "提交": git_state(),
        "时间": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        "运行目录": runs_dir.relative_to(REPO_ROOT).as_posix(),
    }


def output_file(requested: str | None, runs_dir: Path, *, partial: bool) -> Path:
    """结果文件：指定了就用它；否则全部用例写 docs/EVAL_RESULTS.md，部分用例写在运行目录里。"""
    if requested:
        return Path(requested)
    return runs_dir / "EVAL_PARTIAL.md" if partial else DEFAULT_OUTPUT


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--cases", help="只跑这些用例（逗号分隔的编号），默认全部")
    parser.add_argument("--output", help="结果文件，默认见上面的说明")
    parser.add_argument(
        "--repeats", type=int, help="每个用例最多重复几次（调试用，默认按用例文件）"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    settings = load_settings(SETTINGS_FILE).llm
    try:
        llm = create_llm_client(settings)
    except ReactorAgentError as error:
        print(f"错误：{error.code.value}：{error.message}", file=sys.stderr)
        return EXIT_NO_KEY
    wanted = set(args.cases.split(",")) if args.cases else None
    cases = [case for case in load_cases(CASES_DIR) if wanted is None or case.id in wanted]
    if args.repeats:
        cases = [c.model_copy(update={"repeats": min(c.repeats, args.repeats)}) for c in cases]
    skill = load_skill(SKILLS_DIR, SELECTION_SKILL)
    runs_dir = REPO_ROOT / "runs" / f"evals-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    runs_dir.mkdir(parents=True)
    records = run_all(llm, cases, runs_dir, load_rules(skill, SelectionRules))
    output = output_file(args.output, runs_dir, partial=wanted is not None)
    report = render_report(cases, records, metadata(settings, skill, runs_dir))
    output.write_text(report + render_spec_report(cases, records), encoding="utf-8")
    passed = summarize(cases, records).gate_passed and spec_gate(cases, records)
    print(f"\n{'门槛通过' if passed else '门槛没有通过'}，结果写在 {output}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
