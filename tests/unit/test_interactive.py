"""交互入口：密钥只读一次、不回显不打印、菜单把选择变成正确的命令。

输入和子进程都用假的，所以不需要终端、密钥或网络。
"""

import sys

import interactive
import pytest

from reactor_agent.spec.settings import load_settings

VARIABLE = load_settings(interactive.SETTINGS_FILE).llm.api_key_env
SECRET = "sk-secret-value-123456"


class Console:
    """假的终端：按脚本回答密钥和每个提问，记录运行过的命令。"""

    def __init__(self, answers: list[str], secret: str = SECRET) -> None:
        self.answers = answers
        self.secret = secret
        self.secret_prompts: list[str] = []
        self.commands: list[list[str]] = []
        self.environment_seen: list[str | None] = []

    def ask_secret(self, prompt: str) -> str:
        self.secret_prompts.append(prompt)
        return self.secret

    def ask_line(self, _prompt: str) -> str:
        return self.answers.pop(0)

    def run(self, command) -> int:
        self.commands.append(list(command))
        self.environment_seen.append(interactive.os.environ.get(VARIABLE))
        return 0

    def session(self) -> int:
        return interactive.session(self.ask_secret, self.ask_line, self.run)


@pytest.fixture(autouse=True)
def no_key_in_the_environment(monkeypatch):
    monkeypatch.delenv(VARIABLE, raising=False)


def script_names(console: Console) -> list[str]:
    return [command[1].replace("\\", "/").split("/")[-1] for command in console.commands]


def test_the_key_is_asked_once_hidden_and_never_printed(capsys):
    console = Console(["q"])
    assert console.session() == 0
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err
    assert len(console.secret_prompts) == 1 and VARIABLE in console.secret_prompts[0]
    assert f"长度 {len(SECRET)}" in out.out


def test_the_key_reaches_the_commands_through_the_environment_only():
    console = Console(["1", "q"])
    console.session()
    assert console.environment_seen == [SECRET]
    assert all(SECRET not in part for command in console.commands for part in command)


def test_a_key_already_in_the_environment_is_used_without_asking(monkeypatch, capsys):
    monkeypatch.setenv(VARIABLE, SECRET)
    console = Console(["q"])
    assert console.session() == 0
    assert console.secret_prompts == [] and "已有的密钥" in capsys.readouterr().out


def test_an_empty_key_ends_the_session_without_running_anything(capsys):
    console = Console(["1"], secret="   ")
    assert console.session() == 2
    assert console.commands == [] and "没有输入密钥" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("choice", "script"),
    [("1", "e18_llm_structured.py"), ("2", "demo_scenarios.py"), ("3", "run_evals.py")],
)
def test_a_menu_choice_runs_its_script(choice, script):
    console = Console([choice, "q"])
    console.session()
    assert script_names(console) == [script]
    assert console.commands[0][0] == sys.executable


def test_all_runs_the_scenario_demo_and_the_evaluation_and_reports_each_exit_code(capsys):
    console = Console(["a", "q"])
    console.session()
    assert script_names(console) == ["demo_scenarios.py", "run_evals.py"]
    assert "步骤 2：退出码 0" in capsys.readouterr().out


def test_a_description_typed_in_runs_a_dry_run_selection_with_the_text_as_an_argument():
    console = Console(["4", "我想模拟一个反应釜里的酯化反应", "q"])
    console.session()
    [command] = console.commands
    assert command[-3:] == ["run", "我想模拟一个反应釜里的酯化反应", "--dry-run"]
    assert "--text-file" not in command


def test_a_path_typed_in_is_passed_as_a_description_file(tmp_path):
    description = tmp_path / "描述.txt"
    description.write_text("一段描述", encoding="utf-8")
    console = Console(["4", f'"{description}"', "q"])
    console.session()
    [command] = console.commands
    assert command[-4:] == ["run", "--text-file", str(description.resolve()), "--dry-run"]


def test_specific_eval_cases_are_rerun_with_the_cases_option_only():
    console = Console(["5", "L1-S1, L1-K1", "q"])
    console.session()
    [command] = console.commands
    assert command[-2:] == ["--cases", "L1-S1,L1-K1"] and "--output" not in command


def test_empty_answers_and_unknown_choices_run_nothing_and_stay_in_the_menu(capsys):
    console = Console(["4", "", "5", "", "zzz", "q"])
    assert console.session() == 0
    assert console.commands == [] and "不认识的选择" in capsys.readouterr().out


def test_without_a_terminal_it_refuses_instead_of_waiting_for_input(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    assert interactive.main() == 2
    assert "交互式终端" in capsys.readouterr().err
