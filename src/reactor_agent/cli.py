"""命令行入口，也是唯一的装配点：创建具体的 Backend，连起工具、状态存储、Trace 和执行器。

reactor-agent run --spec <规格文件>   建模、求解、验证，打印结果摘要
reactor-agent trace <task_id>          打印一次运行的时间线

其他模块都不导入这个文件。HYSYS 的 Backend 在装配函数里才导入，所以没有 HYSYS 的机器上
“规格文件非法”这类路径照样能运行和测试。
"""

import argparse
import io
import logging
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

from reactor_agent.backends.base import SimBackend
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.harness.engine import Dependencies, Engine
from reactor_agent.observability.render import render_failure, render_summary, render_timeline
from reactor_agent.observability.trace import TRACE_FILE, TraceWriter, read_events
from reactor_agent.recipes import RECIPES
from reactor_agent.spec.components import load_component_table
from reactor_agent.spec.enums import TaskStatus
from reactor_agent.spec.model_spec import ModelSpec, load_model_spec
from reactor_agent.spec.results import RunResult
from reactor_agent.state.models import TaskState
from reactor_agent.state.store import ArtifactName, StateStore
from reactor_agent.tools.definitions import register_tools
from reactor_agent.tools.registry import ToolExecutor

# 项目自带的文件以仓库根目录为基准（src/reactor_agent/cli.py 往上两级），不依赖当前目录。
REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENTS_FILE = REPO_ROOT / "config" / "components.yaml"
DEFAULT_RUNS_DIR = REPO_ROOT / "runs"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNSUPPORTED = 3
EXIT_NEEDS_INPUT = 4
EXIT_CODES: Mapping[TaskStatus, int] = {
    TaskStatus.COMPLETE: EXIT_OK,
    TaskStatus.COMPLETE_WITH_WARNINGS: EXIT_OK,
    TaskStatus.FAILED: EXIT_FAILED,
    TaskStatus.UNSUPPORTED: EXIT_UNSUPPORTED,
    TaskStatus.NEEDS_INPUT: EXIT_NEEDS_INPUT,
}


def _use_utf8_streams() -> None:
    """Windows 上输出被重定向时默认编码不是 UTF-8，中文和单位符号会乱码或报错。"""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


@contextmanager
def _hysys() -> Iterator[SimBackend]:
    """本机的 HYSYS Backend；离开时结束自己启动的 HYSYS 实例。"""
    from reactor_agent.backends.hysys_com.backend import HysysComBackend  # 只在装配时导入

    backend = HysysComBackend()
    try:
        yield backend
    finally:
        backend.shutdown()


def run_spec(tools: ToolExecutor, spec: ModelSpec, spec_path: Path, runs_dir: Path) -> int:
    """用这些工具把一份规格跑到终态，打印结果，返回退出码。"""
    store = StateStore(runs_dir)
    engine = Engine(
        Dependencies(
            tools=tools,
            store=store,
            trace=TraceWriter(runs_dir),
            recipes=RECIPES,
            components=load_component_table(COMPONENTS_FILE),
        )
    )
    task = engine.create_task(spec, spec_path)
    engine.run(task)
    return _print_outcome(store, task)


def _run_command(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec).resolve()
    spec = load_model_spec(spec_path)  # 先校验规格，再去连接 HYSYS
    with _hysys() as backend:
        tools = ToolExecutor(register_tools(backend))
        return run_spec(tools, spec, spec_path, Path(args.runs_dir).resolve())


def _print_outcome(store: StateStore, task: TaskState) -> int:
    result = store.read_artifact(task.task_id, ArtifactName.RESULT, RunResult)
    print(render_summary(result))
    run_dir = store.run_dir(task.task_id)
    spec_path = store.artifact_path(task.task_id, ArtifactName.MODEL_SPEC)
    report = task.failure_report(run_dir / TRACE_FILE, spec_path)
    if report is not None:
        print(render_failure(report), file=sys.stderr)
    print(f"运行目录：{run_dir}")
    return EXIT_CODES[task.status or TaskStatus.FAILED]


def _trace_command(args: argparse.Namespace) -> int:
    path = Path(args.runs_dir).resolve() / args.task_id / TRACE_FILE
    if not path.is_file():
        raise ReactorAgentError(
            ErrorCode.NOT_FOUND, f"没有找到任务 {args.task_id} 的 Trace：{path}"
        )
    print(render_timeline(read_events(path)))
    return EXIT_OK


COMMANDS: Mapping[str, Callable[[argparse.Namespace], int]] = {
    "run": _run_command,
    "trace": _trace_command,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reactor-agent", description="自然语言驱动的反应器建模")
    commands = parser.add_subparsers(dest="command", required=True)
    runs_help = f"运行目录的位置（默认 {DEFAULT_RUNS_DIR}）"
    run = commands.add_parser("run", help="按规格文件建模、求解、验证")
    run.add_argument(
        "--spec", required=True, help="规格文件（YAML 或 JSON，包括某次运行的 model_spec.json）"
    )
    run.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR), help=runs_help)
    trace = commands.add_parser("trace", help="打印一次运行的时间线")
    trace.add_argument("task_id", help="任务标识，即 runs 目录下的目录名")
    trace.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR), help=runs_help)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口。领域错误打印诊断并返回非 0，不让用户只看到 traceback。"""
    _use_utf8_streams()
    logging.basicConfig(level=logging.WARNING)
    args = _parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except ReactorAgentError as error:
        print(f"错误：{error.code.value}：{error.message}", file=sys.stderr)
        for key, value in error.details.items():
            print(f"  {key}：{value}", file=sys.stderr)
        return EXIT_FAILED
