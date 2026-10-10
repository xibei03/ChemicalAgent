"""命令行入口，也是唯一的装配点：创建具体的 Backend 和 LLM 客户端，连起工具、状态存储和执行器。

reactor-agent run --spec <规格文件>            建模、求解、验证，打印结果摘要
reactor-agent run --text-file <描述文件>       读一段反应过程的描述：选型、写规格、建模、求解、验证
reactor-agent run --text-file <文件> --dry-run 干跑：打印选型、规格、假设和建模步骤，不碰 HYSYS
reactor-agent trace <task_id>                  打印一次运行的时间线

其他模块都不导入这个文件。HYSYS 的 Backend 和 LLM 供应商在装配函数里才导入，所以没有 HYSYS 或者
没有密钥的机器上，“规格文件非法”这类路径照样能运行和测试。
"""

import argparse
import io
import logging
import os
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from reactor_agent.backends.base import SimBackend
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.harness.engine import Dependencies, Engine, Handler
from reactor_agent.harness.selection import Selector
from reactor_agent.harness.specify import Specifier
from reactor_agent.llm.client import LlmClient, StructuredClient
from reactor_agent.observability.render import (
    render_failure,
    render_selection,
    render_summary,
    render_timeline,
)
from reactor_agent.observability.render_spec import (
    render_assumptions,
    render_model_spec,
    render_plan,
)
from reactor_agent.observability.trace import TRACE_FILE, TraceWriter, read_events
from reactor_agent.recipes import RECIPES
from reactor_agent.spec.components import load_component_table
from reactor_agent.spec.enums import TaskStatus, WorkflowState
from reactor_agent.spec.loading import read_text_file
from reactor_agent.spec.model_spec import ModelSpec, load_model_spec
from reactor_agent.spec.plan import BuildPlan
from reactor_agent.spec.results import RunResult
from reactor_agent.spec.selection import SelectionResult
from reactor_agent.spec.settings import LlmSettings, load_settings
from reactor_agent.spec.units import load_unit_table
from reactor_agent.state.models import TaskState
from reactor_agent.state.store import ArtifactName, StateStore
from reactor_agent.tools.definitions import register_tools
from reactor_agent.tools.registry import ToolExecutor

# 项目自带的文件以仓库根目录为基准（src/reactor_agent/cli.py 往上两级），不依赖当前目录。
REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENTS_FILE = REPO_ROOT / "config" / "components.yaml"
SETTINGS_FILE = REPO_ROOT / "config" / "settings.yaml"
UNITS_FILE = REPO_ROOT / "config" / "units.yaml"
SKILLS_DIR = REPO_ROOT / "skills"
DEFAULT_RUNS_DIR = REPO_ROOT / "runs"
# 在没有设置密钥时告诉用户怎么在自己的终端里设置：输入时不回显，密钥只留在这个终端会话里。
API_KEY_HINT = "python evals/set_api_key.py（输入一次，测试连通后永久保存，新开的终端就能读到）"

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


def create_llm_client(settings: LlmSettings) -> LlmClient:
    """按配置创建 LLM 客户端。密钥只从环境变量读，读不到就说明怎么设置。"""
    api_key = os.environ.get(settings.api_key_env, "")
    if not api_key:
        hint = API_KEY_HINT.format(variable=settings.api_key_env)
        raise ReactorAgentError(
            ErrorCode.LLM,
            f"环境变量 {settings.api_key_env} 没有设置，没法调用 LLM",
            {"在自己的终端里设置（输入时不回显），然后重新运行": hint},
        )
    from reactor_agent.llm.providers.dashscope import DashScopeProvider  # 只在需要时导入

    return StructuredClient(DashScopeProvider(settings, api_key))


def _engine(
    tools: ToolExecutor,
    store: StateStore,
    trace: TraceWriter,
    handlers: Mapping[WorkflowState, Handler],
) -> Engine:
    deps = Dependencies(
        tools=tools,
        store=store,
        trace=trace,
        recipes=RECIPES,
        components=load_component_table(COMPONENTS_FILE),
        extra_handlers=handlers,
    )
    return Engine(deps)


def run_spec(tools: ToolExecutor, spec: ModelSpec, spec_path: Path, runs_dir: Path) -> int:
    """用这些工具把一份规格跑到终态，打印结果，返回退出码。"""
    store = StateStore(runs_dir)
    engine = _engine(tools, store, TraceWriter(runs_dir), handlers={})
    task = engine.create_task(spec, spec_path)
    engine.run(task)
    return _print_outcome(store, task)


@dataclass(frozen=True)
class TextRun:
    """从文字描述开始的任务用的一套对象：创建任务的 Selector、执行器、状态存储。"""

    selector: Selector
    engine: Engine
    store: StateStore


def build_text_run(llm: LlmClient, runs_dir: Path, tools: ToolExecutor | None = None) -> TextRun:
    """装配文字描述的运行：选型、写规格、校验三个调用 LLM 或规格的状态，加上建模用的工具。

    没有给工具时是空工具集：只能走到建模之前（干跑和评测用），不创建 Backend。
    """
    store = StateStore(runs_dir)
    trace = TraceWriter(runs_dir)
    components = load_component_table(COMPONENTS_FILE)
    selector = Selector(llm, store, trace, RECIPES, SKILLS_DIR)
    specifier = Specifier(
        llm, store, trace, RECIPES, SKILLS_DIR, components, load_unit_table(UNITS_FILE)
    )
    handlers = {
        WorkflowState.SELECT: selector.run,
        WorkflowState.SPECIFY: specifier.specify,
        WorkflowState.VALIDATE: specifier.validate,
    }
    engine = _engine(tools or ToolExecutor({}), store, trace, handlers)
    return TextRun(selector, engine, store)


def run_text(
    llm: LlmClient, text: str, runs_dir: Path, *, dry_run: bool, tools: ToolExecutor | None = None
) -> int:
    """文字描述的任务：干跑停在建模之前（PLAN 之后），否则跑到终态；打印并返回退出码。"""
    run = build_text_run(llm, runs_dir, tools)
    task = run.selector.create_task(text)
    run.engine.run(task, stop_at=WorkflowState.PREFLIGHT if dry_run else None)
    return _print_text_outcome(run.store, task, dry_run=dry_run)


def _text_of(args: argparse.Namespace) -> str:
    """命令行给的描述：文件，或者直接作为参数。"""
    if args.text_file is not None:
        return read_text_file(Path(args.text_file).resolve())
    if not args.text.strip():
        raise ReactorAgentError(ErrorCode.SCHEMA, "给的描述是空的，没有可模拟的内容")
    return str(args.text).strip()


def _run_command(args: argparse.Namespace) -> int:
    runs_dir = Path(args.runs_dir).resolve()
    if args.spec is not None:
        if args.dry_run:
            raise ReactorAgentError(
                ErrorCode.SCHEMA, "--dry-run 只用于文字描述，规格文件没有选型这一步"
            )
        spec_path = Path(args.spec).resolve()
        spec = load_model_spec(spec_path)  # 先校验规格，再去连接 HYSYS
        with _hysys() as backend:
            return run_spec(ToolExecutor(register_tools(backend)), spec, spec_path, runs_dir)
    text = _text_of(args)  # 先读描述，再去连 LLM
    llm = create_llm_client(load_settings(SETTINGS_FILE).llm)
    if args.dry_run:
        return run_text(llm, text, runs_dir, dry_run=True)
    with _hysys() as backend:
        tools = ToolExecutor(register_tools(backend))
        return run_text(llm, text, runs_dir, dry_run=False, tools=tools)


def _print_outcome(store: StateStore, task: TaskState) -> int:
    result = store.read_artifact(task.task_id, ArtifactName.RESULT, RunResult)
    print(render_summary(result))
    run_dir = store.run_dir(task.task_id)
    spec_path = store.artifact_path(task.task_id, ArtifactName.MODEL_SPEC)
    report = task.failure_report(run_dir / TRACE_FILE, spec_path)
    if report is not None:
        print(render_failure(report), file=sys.stderr)
    print(f"运行目录：{run_dir}")
    return EXIT_FAILED if task.status is None else EXIT_CODES[task.status]  # 没走到终态不算成功


def _print_text_outcome(store: StateStore, task: TaskState, *, dry_run: bool) -> int:
    """打印选型结论、换算后的规格、假设清单和建模步骤（哪一步有就打印哪一步）；然后按终态返回。"""
    if store.artifact_path(task.task_id, ArtifactName.SELECTION).is_file():
        selection = store.read_artifact(task.task_id, ArtifactName.SELECTION, SelectionResult)
        print(render_selection(selection))
    if store.artifact_path(task.task_id, ArtifactName.MODEL_SPEC).is_file():
        spec = store.read_artifact(task.task_id, ArtifactName.MODEL_SPEC, ModelSpec)
        print(f"\n{render_model_spec(spec)}\n\n{render_assumptions(spec)}")
    if store.artifact_path(task.task_id, ArtifactName.PLAN).is_file():
        plan = store.read_artifact(task.task_id, ArtifactName.PLAN, BuildPlan)
        print(f"\n{render_plan(plan)}")
    if task.status is None and dry_run:
        print(f"\n干跑：到建模步骤为止，没有连接 HYSYS。运行目录：{store.run_dir(task.task_id)}")
        return EXIT_OK
    return _print_outcome(store, task)


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
    run = commands.add_parser("run", help="按规格文件建模，或者读一段描述做选型")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--spec", help="规格文件（YAML 或 JSON，包括某次运行的 model_spec.json）")
    source.add_argument("--text-file", help="一段反应过程的描述，UTF-8 编码的文本文件")
    source.add_argument(
        "text",
        nargs="?",
        help="直接给出描述。较长的文字用 --text-file：带引号的中文容易被 shell 改坏",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="只选型，打印结果后停下，不碰 HYSYS（只用于文字描述）",
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
