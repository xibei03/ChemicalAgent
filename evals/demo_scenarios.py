"""对三个考核场景的原文各执行一次 `reactor-agent run --text-file ... --dry-run`，输出留作证据。

和命令行是同一条路径（调用 cli.main）。需要 LLM 密钥：
  python evals/demo_scenarios.py [--ask-key]
--ask-key：环境变量里没有密钥时在终端里提示输入（不回显，只留在这个进程的内存里）。
输出：evals/out/dry_run_scenarios.txt（选型结果、理由、原文依据和备选；不含密钥）。
退出码：三个都以 0 结束是 0。
"""

import argparse
import contextlib
import getpass
import io
import os
import sys

from reactor_agent.cli import REPO_ROOT, SETTINGS_FILE, main
from reactor_agent.spec.settings import load_settings

INPUTS = REPO_ROOT / "evals" / "inputs"
OUTPUT = REPO_ROOT / "evals" / "out" / "dry_run_scenarios.txt"
EXPECTED = ("Equilibrium", "Conversion", "Gibbs")


def run_one(number: int, expected: str) -> tuple[bool, str]:
    """跑一个场景，返回（是否以 0 退出并得到期望的类型, 输出全文）。"""
    command = f"reactor-agent run --text-file evals/inputs/scenario-{number}.txt --dry-run"
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(["run", "--text-file", str(INPUTS / f"scenario-{number}.txt"), "--dry-run"])
    text = f"$ {command}\n{out.getvalue()}{err.getvalue()}退出码：{code}\n"
    return code == 0 and f"选型结论：{expected}" in out.getvalue(), text


def cli_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ask-key", action="store_true")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    variable = load_settings(SETTINGS_FILE).llm.api_key_env
    if not os.environ.get(variable) and args.ask_key:
        os.environ[variable] = getpass.getpass(f"请输入 {variable}（输入时不显示）：").strip()
    results = [run_one(number, kind) for number, kind in enumerate(EXPECTED, start=1)]
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text("\n".join(text for _, text in results), encoding="utf-8")
    print(OUTPUT.read_text(encoding="utf-8"))
    for number, (passed, _) in enumerate(results, start=1):
        verdict = f"得到期望的 {EXPECTED[number - 1]}" if passed else "没有得到期望的结果"
        print(f"场景 {number}：{verdict}")
    return 0 if all(passed for passed, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(cli_main())
