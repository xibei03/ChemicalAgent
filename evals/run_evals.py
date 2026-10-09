"""运行选型评测：每个用例跑真实的选型（和 `run --dry-run` 同一条路径），打分，写评测结果文件。

三个原文场景各重复 5 次，其余用例各 1 次（次数写在用例文件里）。需要 LLM 密钥：
  python evals/run_evals.py [--ask-key] [--cases L1-S1,L1-K1] [--output docs/EVAL_RESULTS.md]
密钥只从环境变量读（名字在 config/settings.yaml）；--ask-key 是环境变量里没有时在终端里提示输入，
不回显，只留在这个进程的内存里。每次运行的目录在 runs/evals-<时间>/ 下，有 LLM 的提示和回复全文。
退出码：门槛通过是 0，没通过是 1。
"""

import argparse
import getpass
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from scoring import EvalCase, RunRecord, load_cases, render_report, summarize

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
from reactor_agent.skill_loader import load_rules, load_skill
from reactor_agent.spec.enums import WorkflowState
from reactor_agent.spec.llm import LlmCallRecord
from reactor_agent.spec.selection import SelectionDraft, SelectionResult, SelectionRules
from reactor_agent.spec.selection_rules import check_rules
from reactor_agent.spec.settings import load_settings
from reactor_agent.state.store import ArtifactName

CASES_DIR = REPO_ROOT / "evals" / "cases"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "EVAL_RESULTS.md"


def read_logs(run_dir: Path) -> list[LlmCallRecord]:
    """这次运行里按顺序的全部 LLM 调用记录（select-1、select-2……）。"""
    files = sorted((run_dir / "llm").glob("select-*.json"), key=lambda p: int(p.stem.split("-")[1]))
    return [LlmCallRecord.model_validate_json(f.read_text(encoding="utf-8")) for f in files]


def run_one(
    llm: LlmClient, case: EvalCase, repeat: int, runs_dir: Path, rules: SelectionRules
) -> RunRecord:
    """跑一次选型，收集打分需要的东西。"""
    selector, engine, store = build_text_run(llm, runs_dir)
    started = time.monotonic()
    task = selector.create_task(case.input)
    engine.run(task, stop_at=WorkflowState.SPECIFY)
    seconds = time.monotonic() - started
    run_dir = store.run_dir(task.task_id)
    path = store.artifact_path(task.task_id, ArtifactName.SELECTION)
    selection = (
        store.read_artifact(task.task_id, ArtifactName.SELECTION, SelectionResult)
        if path.is_file()
        else None
    )
    logs = read_logs(run_dir)
    first = SelectionDraft.model_validate_json(logs[0].attempts[-1].reply_text) if logs else None
    first_rule = (
        check_rules(first.features, rules, first.recommended_type).reactor_type if first else None
    )
    return RunRecord(
        case_id=case.id,
        repeat=repeat,
        selection=selection,
        first_recommendation=first.recommended_type if first else None,
        first_rule_type=first_rule,
        has_first_answer=first is not None,
        error=task.errors[-1].message if task.errors else None,
        tokens=sum(log.total_tokens for log in logs),
        seconds=seconds,
        reasked=len(logs) > 1,
    )


def git_state() -> str:
    """提交哈希，工作区有未提交改动时注明。"""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        ).stdout.strip()

    dirty = "，有未提交的改动" if git("status", "--porcelain") else ""
    return f"{git('rev-parse', '--short', 'HEAD')}{dirty}"


def result_file(runs_dir: Path, *, partial: bool) -> Path:
    """跑全部用例写 docs/EVAL_RESULTS.md；只跑一部分写在运行目录里，不覆盖完整的结果。"""
    return runs_dir / "EVAL_PARTIAL.md" if partial else DEFAULT_OUTPUT


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--ask-key", action="store_true", help="环境变量里没有密钥时在终端里输入")
    parser.add_argument("--cases", help="只跑这些用例（逗号分隔的编号），默认全部")
    parser.add_argument(
        "--output", help="结果文件。默认：全部用例写 docs/EVAL_RESULTS.md，部分用例写在运行目录里"
    )
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    settings = load_settings(SETTINGS_FILE).llm
    if not os.environ.get(settings.api_key_env) and args.ask_key:
        os.environ[settings.api_key_env] = getpass.getpass(
            f"请输入 {settings.api_key_env}（输入时不显示）："
        ).strip()
    try:
        llm = create_llm_client(settings)
    except ReactorAgentError as error:
        print(f"错误：{error.code.value}：{error.message}", file=sys.stderr)
        return 2
    cases = load_cases(CASES_DIR)
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [case for case in cases if case.id in wanted]
    skill = load_skill(SKILLS_DIR, SELECTION_SKILL)
    rules = load_rules(skill, SelectionRules)
    runs_dir = REPO_ROOT / "runs" / f"evals-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    runs_dir.mkdir(parents=True)
    records = []
    for case in cases:
        for repeat in range(1, case.repeats + 1):
            record = run_one(llm, case, repeat, runs_dir, rules)
            records.append(record)
            mark = "✓" if record.selection and record.final_type == case.expected.reactor else "✗"
            where = f"第 {repeat}/{case.repeats} 次"
            print(
                f"{mark} {case.id} {where}：{record.final_type}（{record.seconds:.1f} 秒）",
                flush=True,
            )
    meta = {
        "模型": settings.model,
        "Skill": f"{skill.name} {skill.version}（内容哈希 {skill.content_hash[:12]}）",
        "提交": git_state(),
        "时间": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        "运行目录": runs_dir.relative_to(REPO_ROOT).as_posix(),
    }
    report = render_report(cases, records, meta)
    output = Path(args.output) if args.output else result_file(runs_dir, partial=bool(args.cases))
    output.write_text(report, encoding="utf-8")
    summary = summarize(cases, records)
    print(f"\n{'门槛通过' if summary.gate_passed else '门槛没有通过'}，结果写在 {output}")
    return 0 if summary.gate_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
