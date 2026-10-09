"""E17（1C 任务 9）：建模中途结束 HYSYS 进程，执行器会怎样？

要回答：
  Q1 进程被结束之后，执行器在多长时间内以 FAILED 结束？（要求 60 秒内）
  Q2 终态和诊断是否说明会话已失效，并给出用同一份冻结规格重跑的命令？
  Q3 照诊断里的命令重跑（命令行 run），能完成吗？
  Q4 中止之后命令行的收尾（结束 HYSYS 实例）有没有卡住、有没有留下 HYSYS 进程？

做法：用生产代码的 Backend、ToolExecutor 和执行器；包装 ToolExecutor，在第 N 次工具调用成功之后
`taskkill /F /PID <进程号>`（进程号取自 session.connect 的结果）。这不是自动化测试：它会破坏测试
会话共用的连接，所以只作为一次性的探针。运行目录放在临时目录，只把输出文本留在 spikes/out/。

用法：python spikes/e17_session_loss.py [--after N] [--spec 规格名] [--tag 名字]
输出：spikes/out/e17_session_loss_<tag>.txt
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from _common import Log, hysys_processes, use_utf8

from reactor_agent.cli import COMPONENTS_FILE, _hysys
from reactor_agent.harness.engine import Dependencies, Engine
from reactor_agent.observability.render import render_failure, render_timeline
from reactor_agent.observability.trace import TRACE_FILE, TraceWriter, read_events
from reactor_agent.recipes import RECIPES
from reactor_agent.spec.components import load_component_table
from reactor_agent.spec.enums import ToolName
from reactor_agent.spec.model_spec import load_model_spec
from reactor_agent.spec.tool_results import ToolResult
from reactor_agent.state.store import ArtifactName, StateStore
from reactor_agent.tools.definitions import register_tools
from reactor_agent.tools.registry import ToolExecutor

use_utf8()

GOLDEN = Path(__file__).resolve().parents[1] / "evals" / "golden_specs"
DEADLINE_S = 60
RERUN_TIMEOUT_S = 300


class KillAfter(ToolExecutor):
    """第 N 次工具调用成功之后结束 HYSYS 进程。"""

    def __init__(self, inner: ToolExecutor, after: int, log: Log) -> None:
        super().__init__({})
        self._inner = inner
        self._after = after
        self._log = log
        self._count = 0
        self._pid: int | None = None
        self.killed_at: float | None = None

    def call(self, name: str, args: object) -> ToolResult:
        result = self._inner.call(name, args)
        self._count += 1
        if name == ToolName.SESSION_CONNECT and result.ok:
            self._pid = result.data.process_id
        if self._count == self._after and self._pid is not None:
            self._log.say(f"  第 {self._count} 次调用（{name}）之后结束进程 {self._pid}")
            subprocess.run(["taskkill", "/F", "/PID", str(self._pid)], capture_output=True)
            self.killed_at = time.monotonic()
        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--after", type=int, default=9)
    parser.add_argument("--spec", default="smr_equilibrium")
    parser.add_argument("--tag", default="run1")
    args = parser.parse_args()
    log = Log(f"e17_session_loss_{args.tag}")
    runs = Path(tempfile.mkdtemp(prefix="e17_runs_"))
    spec_file = GOLDEN / f"{args.spec}.yaml"
    spec = load_model_spec(spec_file)
    store = StateStore(runs)
    log.say(f"规格 {args.spec}，第 {args.after} 次工具调用之后结束 HYSYS；运行目录 {runs}")
    before = set(hysys_processes())
    with _hysys() as backend:
        tools = KillAfter(ToolExecutor(register_tools(backend)), args.after, log)
        deps = Dependencies(
            tools=tools,
            store=store,
            trace=TraceWriter(runs),
            recipes=RECIPES,
            components=load_component_table(COMPONENTS_FILE),
        )
        engine = Engine(deps)
        task = engine.create_task(spec, spec_file)
        engine.run(task)
        ended = time.monotonic()
    assert tools.killed_at is not None, "进程没有被结束，--after 可能超过了总调用数"
    elapsed = ended - tools.killed_at
    log.say(f"终态 {task.status.value}，从结束进程到离开 HYSYS 收尾共 {elapsed:.1f} 秒")
    leftover = set(hysys_processes()) - before
    log.say(f"收尾之后多出来的 HYSYS 进程：{sorted(leftover) or '没有'}")
    trace_path = store.run_dir(task.task_id) / TRACE_FILE
    spec_path = store.artifact_path(task.task_id, ArtifactName.MODEL_SPEC)
    report = task.failure_report(trace_path, spec_path)
    assert report is not None
    diagnosis = render_failure(report)
    log.say("--- 诊断 ---")
    log.say(diagnosis)
    log.say("--- 时间线 ---")
    log.say(render_timeline(read_events(trace_path)))
    command = re.search(r'reactor-agent run --spec "(.+)"', diagnosis)
    log.say("--- 照诊断里的命令重跑 ---")
    if command is None:
        log.conclude("Q2 否：诊断里没有重跑的命令")
        return
    exe = Path(sys.executable).parent / "reactor-agent.exe"
    rerun = subprocess.run(
        [str(exe), "run", "--spec", command.group(1), "--runs-dir", str(runs)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=RERUN_TIMEOUT_S,
    )
    log.say(f"退出码 {rerun.returncode}")
    log.say("\n".join(rerun.stdout.splitlines()[:6]))
    log.conclude(
        f"Q1 {'是' if elapsed <= DEADLINE_S else '否'}（{elapsed:.1f} 秒，要求 {DEADLINE_S} 秒内，"
        f"终态 {task.status.value}）；Q2 {'是' if report.code.value.startswith('E_COM') else '否'}"
        f"（错误码 {report.code.value}）；Q3 {'是' if rerun.returncode == 0 else '否'}"
        f"（退出码 {rerun.returncode}）；Q4 {'没有' if not leftover else '有'}残留进程"
    )
    shutil.rmtree(runs, ignore_errors=True)  # 临时目录，输出文本已经留在 spikes/out/


if __name__ == "__main__":
    main()
