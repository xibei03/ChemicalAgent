"""命令行的文字入口：--text-file、位置参数、--dry-run、缺密钥、用法错误。

LLM 用桩，ToolExecutor 是空的：这些路径不需要 HYSYS，也不需要密钥。
"""

import pytest

from builders import conversion_scenario
from fake_llm import FakeLlm
from fake_tools import FakeTools
from reactor_agent import cli
from reactor_agent.cli import EXIT_FAILED, EXIT_OK, EXIT_UNSUPPORTED, main, run_text
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import ReactorType
from reactor_agent.spec.selection import FeatureName as F
from selection_builders import evidence_text, make_draft, make_features
from task_builders import conversion_task, equilibrium_task

EQUILIBRIUM_FEATURES = make_features(F.REACTION_DEFINED)
TEXT = evidence_text(EQUILIBRIUM_FEATURES)
CONVERSION_FEATURES = make_features(F.CONVERSION_DATA_GIVEN, F.REACTION_DEFINED)
# 原文里要有 TaskSpec 里用户给的那些数：抄写检查会核对。
CONVERSION_TEXT = (
    evidence_text(CONVERSION_FEATURES) + "。进料 10000 kg/h，380 ℃，2.5 MPa，转化率 50%。"
)


def equilibrium_llm() -> FakeLlm:
    """先回选型，再回 TaskSpec。TEXT 里没有数字，抄写检查不查。"""
    return FakeLlm([make_draft(EQUILIBRIUM_FEATURES, ReactorType.EQUILIBRIUM), equilibrium_task()])


def only_run(runs_dir):
    return next(path for path in runs_dir.iterdir() if path.is_dir())


def test_a_dry_run_prints_the_type_the_reasons_the_evidence_and_the_alternatives(tmp_path, capsys):
    code = run_text(equilibrium_llm(), TEXT, tmp_path, dry_run=True)
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "选型结论：Equilibrium" in out and "规则的推导" in out and "LLM 的理由" in out
    assert "原文依据：" in out and "“原文reaction_defined”" in out
    assert "备选类型：" in out and "Gibbs（能建）" in out and "PFR（不能建）" in out
    assert "规格（已换算成规范单位" in out and "假设（" in out and "建模步骤（" in out
    assert "运行目录：" in out and "没有连接 HYSYS" in out


def test_a_dry_run_stops_before_any_tool_is_called_and_ends_at_the_plan(tmp_path):
    run = cli.build_text_run(equilibrium_llm(), tmp_path)
    task = run.selector.create_task(TEXT)
    run.engine.run(task, stop_at=cli.WorkflowState.PREFLIGHT)
    assert task.status is None and task.current_state is cli.WorkflowState.PREFLIGHT
    assert task.spec_hash is not None and task.case_names == ("T700", "T600")


def test_without_dry_run_the_task_goes_on_to_the_tools_and_completes(tmp_path, capsys):
    scenario = conversion_scenario()
    llm = FakeLlm([make_draft(CONVERSION_FEATURES, ReactorType.CONVERSION), conversion_task()])
    tools = FakeTools([scenario.snapshot])
    code = run_text(llm, CONVERSION_TEXT, tmp_path, dry_run=False, tools=tools)
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "选型结论：Conversion" in out and "complete" in out
    assert tools.solves == 1


def test_a_request_that_is_not_a_reaction_prints_the_selection_and_exits_unsupported(
    tmp_path, capsys
):
    features = make_features(reaction_process=False)
    llm = FakeLlm([make_draft(features, None)])
    code = run_text(llm, "请模拟一座精馏塔", tmp_path, dry_run=True)
    captured = capsys.readouterr()
    assert code == EXIT_UNSUPPORTED
    assert "选型结论：无" in captured.out
    assert "E_UNSUPPORTED" in captured.err and "不是反应过程" in captured.err


def test_nothing_in_a_dry_run_touches_hysys(tmp_path, monkeypatch):
    def refuse() -> None:
        raise AssertionError("dry-run 不应该创建 Backend")

    monkeypatch.setattr(cli, "_hysys", refuse)
    monkeypatch.setattr(cli, "create_llm_client", lambda _settings: equilibrium_llm())
    description = tmp_path / "d.txt"
    description.write_text(TEXT, encoding="utf-8")
    arguments = ["run", "--text-file", str(description), "--dry-run"]
    assert main([*arguments, "--runs-dir", str(tmp_path / "runs")]) == EXIT_OK


def test_main_reads_the_description_from_a_utf8_file_and_stops_after_selection(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "create_llm_client", lambda _settings: equilibrium_llm())
    description = tmp_path / "描述.txt"
    description.write_text(TEXT + "\n", encoding="utf-8")
    runs = tmp_path / "runs"
    code = main(["run", "--text-file", str(description), "--dry-run", "--runs-dir", str(runs)])
    assert code == EXIT_OK
    assert "选型结论：Equilibrium" in capsys.readouterr().out
    assert (only_run(runs) / "artifacts" / "input.txt").read_text(encoding="utf-8") == TEXT


def test_main_accepts_the_description_as_a_positional_argument(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "create_llm_client", lambda _settings: equilibrium_llm())
    code = main(["run", TEXT, "--dry-run", "--runs-dir", str(tmp_path / "runs")])
    assert code == EXIT_OK and "选型结论：Equilibrium" in capsys.readouterr().out


def test_a_file_with_a_bom_is_read_without_the_bom(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "create_llm_client", lambda _settings: equilibrium_llm())
    description = tmp_path / "bom.txt"
    description.write_bytes(b"\xef\xbb\xbf" + TEXT.encode("utf-8"))
    runs = tmp_path / "runs"
    main(["run", "--text-file", str(description), "--dry-run", "--runs-dir", str(runs)])
    assert (only_run(runs) / "artifacts" / "input.txt").read_text(encoding="utf-8") == TEXT


@pytest.mark.parametrize("content", [b"", b"   \n  ", b"\xff\xfe\x00bad"])
def test_an_empty_or_non_utf8_description_is_a_schema_error_and_never_calls_the_llm(
    content, tmp_path, monkeypatch, capsys
):
    def refuse(_settings: object) -> None:
        raise AssertionError("描述不合法时不该去创建 LLM 客户端")

    monkeypatch.setattr(cli, "create_llm_client", refuse)
    description = tmp_path / "bad.txt"
    description.write_bytes(content)
    code = main(["run", "--text-file", str(description), "--runs-dir", str(tmp_path / "runs")])
    err = capsys.readouterr().err
    assert code == EXIT_FAILED and "E_SCHEMA" in err and "Traceback" not in err


def test_a_missing_description_file_is_an_io_error(tmp_path, capsys):
    code = main(["run", "--text-file", str(tmp_path / "nope.txt"), "--runs-dir", str(tmp_path)])
    assert code == EXIT_FAILED and "E_IO" in capsys.readouterr().err


def test_a_missing_api_key_names_the_variable_and_how_to_set_it_without_a_traceback(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    description = tmp_path / "d.txt"
    description.write_text(TEXT, encoding="utf-8")
    arguments = ["run", "--text-file", str(description), "--dry-run"]
    code = main([*arguments, "--runs-dir", str(tmp_path / "runs")])
    err = capsys.readouterr().err
    assert code == EXIT_FAILED
    assert "E_LLM" in err and "DASHSCOPE_API_KEY" in err and "set_api_key.py" in err
    assert "Traceback" not in err
    assert not (tmp_path / "runs").exists()


def test_the_key_comes_only_from_the_environment_and_is_never_in_the_settings_file(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-not-a-real-key")
    llm = cli.create_llm_client(cli.load_settings(cli.SETTINGS_FILE).llm)
    assert hasattr(llm, "complete")
    assert "sk-test" not in cli.SETTINGS_FILE.read_text(encoding="utf-8")


def test_dry_run_with_a_spec_file_is_refused(tmp_path, capsys):
    spec = tmp_path / "s.yaml"
    spec.write_text("reactor_type: gibbs\n", encoding="utf-8")
    code = main(["run", "--spec", str(spec), "--dry-run", "--runs-dir", str(tmp_path)])
    assert code == EXIT_FAILED and "--dry-run 只用于文字描述" in capsys.readouterr().err


@pytest.mark.parametrize(
    "arguments",
    [
        ["run"],
        ["run", "--spec", "a.yaml", "--text-file", "b.txt"],
        ["run", "描述", "--spec", "a.yaml"],
        ["run", "描述", "--text-file", "b.txt"],
    ],
)
def test_exactly_one_source_of_input_is_required(arguments, capsys):
    with pytest.raises(SystemExit) as caught:
        main(arguments)
    assert caught.value.code != 0
    assert "Traceback" not in capsys.readouterr().err


def test_an_llm_failure_prints_the_diagnosis_and_exits_non_zero(tmp_path, capsys):
    llm = FakeLlm([ReactorAgentError(ErrorCode.LLM, "网络不通")])
    code = run_text(llm, TEXT, tmp_path, dry_run=True)
    captured = capsys.readouterr()
    assert code == EXIT_FAILED
    assert "E_LLM" in captured.err and "网络不通" in captured.err
    assert "选型结论" not in captured.out


@pytest.mark.parametrize("flag", ["--text-file", "--spec"])
def test_an_empty_path_argument_is_a_domain_error_not_a_crash(flag, tmp_path, capsys):
    code = main(["run", flag, "", "--runs-dir", str(tmp_path / "runs")])
    err = capsys.readouterr().err
    assert code == EXIT_FAILED and "E_IO" in err and "Traceback" not in err
    assert not (tmp_path / "runs").exists()


def test_an_empty_positional_description_is_a_schema_error(tmp_path, capsys):
    code = main(["run", "   ", "--runs-dir", str(tmp_path / "runs")])
    assert code == EXIT_FAILED and "E_SCHEMA" in capsys.readouterr().err
