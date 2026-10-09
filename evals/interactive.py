"""交互入口：在终端里输入一次 API 密钥，然后选择要运行的检查。

  python evals/interactive.py

密钥用 getpass 读（输入时不显示），只保存在这个进程的环境里，子进程继承它；不写文件、不进日志、
不回显。系统本身（src/）仍然只从环境变量读密钥，这个入口只是替你设置那个环境变量。
环境变量里已经有密钥时直接使用，不再询问。
"""

import getpass
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from reactor_agent.cli import REPO_ROOT, SETTINGS_FILE
from reactor_agent.spec.settings import load_settings

PYTHON = sys.executable
# 调用命令行入口 reactor-agent 的一行程序（包里没有 __main__）。
CLI_COMMAND = [
    PYTHON,
    "-c",
    "import sys; from reactor_agent.cli import main; sys.exit(main(sys.argv[1:]))",
]


@dataclass(frozen=True)
class Step:
    """菜单里的一项：说明，以及要运行的命令。"""

    title: str
    command: Sequence[str]


STEPS: dict[str, Step] = {
    "1": Step(
        "探针 E18：测 LLM 客户端要用的能力（json_schema、温度 0、关闭思考、超时、错误类型）",
        [PYTHON, str(REPO_ROOT / "spikes" / "e18_llm_structured.py"), "--tag", "run1"],
    ),
    "2": Step(
        "三个考核场景各做一次选型（run --dry-run），输出存进 evals/out/",
        [PYTHON, str(REPO_ROOT / "evals" / "demo_scenarios.py")],
    ),
    "3": Step(
        "选型评测（全部用例，几分钟），结果写进 docs/EVAL_RESULTS.md",
        [PYTHON, str(REPO_ROOT / "evals" / "run_evals.py")],
    ),
}
RUN_ALL = ("2", "3")  # 探针 E18 已经跑过，结果在台账 L39
MENU = (
    *(f"  {key}  {step.title}" for key, step in STEPS.items()),
    "  4  对你输入的一段描述做选型（输入一行文字，或者一个文本文件的路径）",
    "  5  只重跑指定的评测用例（输入编号，逗号分隔），结果不覆盖 docs/EVAL_RESULTS.md",
    "  a  依次运行 2、3",
    "  q  退出",
)

Ask = Callable[[str], str]
Run = Callable[[Sequence[str]], int]


def run_command(command: Sequence[str]) -> int:
    """运行一条命令，输出直接显示在终端里；Ctrl+C 只中断这一条，回到菜单。"""
    try:
        return subprocess.run(command, cwd=REPO_ROOT, check=False).returncode
    except KeyboardInterrupt:
        print("\n已中断。")
        return 130


def describe(text: str) -> list[str]:
    """第 4 项的命令：存在的文件当作描述文件，否则当作描述文字。"""
    given = text.strip().strip('"')
    is_file = bool(given) and Path(given).is_file()
    source = ["--text-file", str(Path(given).resolve())] if is_file else [given]
    return [*CLI_COMMAND, "run", *source, "--dry-run"]


def choose(choice: str, ask_line: Ask, run: Run) -> bool:
    """执行一个菜单选择；返回是不是要继续留在菜单里。"""
    if choice == "q":
        return False
    if choice == "a":
        results = {key: run(STEPS[key].command) for key in RUN_ALL}
        print("\n".join(f"  步骤 {key}：退出码 {code}" for key, code in results.items()))
    elif choice in STEPS:
        run(STEPS[choice].command)
    elif choice == "4":
        text = ask_line("描述（一行文字，或文本文件的路径）：")
        if text.strip():
            run(describe(text))
    elif choice == "5":
        cases = ask_line("评测用例编号（逗号分隔，如 L1-S1,L1-K1）：").replace(" ", "")
        if cases:
            run([PYTHON, str(REPO_ROOT / "evals" / "run_evals.py"), "--cases", cases])
    else:
        print(f"不认识的选择：{choice!r}")
    return True


def session(ask_secret: Ask, ask_line: Ask, run: Run) -> int:
    """读密钥，然后循环显示菜单。返回退出码：没有密钥是 2。"""
    variable = load_settings(SETTINGS_FILE).llm.api_key_env
    if os.environ.get(variable):
        print(f"使用环境变量 {variable} 里已有的密钥。")
    else:
        os.environ[variable] = ask_secret(f"请输入 {variable}（输入时不显示）：").strip()
    if not os.environ[variable]:
        print("没有输入密钥，退出。", file=sys.stderr)
        return 2
    print(f"密钥已读入（长度 {len(os.environ[variable])}），只保存在这个进程的环境里。\n")
    while True:
        print("\n".join(["要运行什么？", *MENU]))
        if not choose(ask_line("选择：").strip().lower(), ask_line, run):
            return 0
        print()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("需要在交互式终端里运行：密钥要在终端里输入。", file=sys.stderr)
        return 2
    return session(getpass.getpass, input, run_command)


if __name__ == "__main__":
    raise SystemExit(main())
