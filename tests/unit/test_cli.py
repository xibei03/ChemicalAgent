"""命令行：非法的规格文件、用桩工具完整运行一次、trace 命令、用某次运行留下的规格重跑。

run_spec 接受 ToolExecutor，所以这里用桩，不需要 HYSYS。
"""

import io
import sys
from pathlib import Path

import pytest

from builders import GOLDEN
from fake_tools import FakeTools
from reactor_agent.cli import (
    EXIT_FAILED,
    EXIT_OK,
    EXIT_UNSUPPORTED,
    _use_utf8_streams,
    main,
    run_spec,
)
from reactor_agent.errors import ErrorCode
from reactor_agent.spec.enums import ToolName
from reactor_agent.spec.model_spec import load_model_spec, spec_hash
from reactor_agent.state.store import ArtifactName, StateStore

GOLDEN_FILE = GOLDEN / "toluene_conversion.yaml"


def only_run(runs_dir: Path) -> str:
    return next(path.name for path in runs_dir.iterdir() if path.is_dir())


def test_a_missing_spec_file_exits_non_zero_with_a_readable_reason(tmp_path, capsys):
    code = main(["run", "--spec", str(tmp_path / "nope.yaml"), "--runs-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert code == EXIT_FAILED
    assert "E_IO" in captured.err and "nope.yaml" in captured.err
    assert "Traceback" not in captured.err + captured.out


def test_an_invalid_spec_names_the_field_and_never_creates_a_run(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("reactor_type: banana\n", encoding="utf-8")
    code = main(["run", "--spec", str(bad), "--runs-dir", str(tmp_path / "runs")])
    captured = capsys.readouterr()
    assert code == EXIT_FAILED
    assert "E_SCHEMA" in captured.err and "reactor_type" in captured.err
    assert "Traceback" not in captured.err + captured.out
    assert not (tmp_path / "runs").exists()


def test_a_spec_that_is_not_a_utf8_text_is_a_schema_error_not_a_traceback(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_bytes("\xff\xfe".encode("latin-1"))
    assert main(["run", "--spec", str(bad), "--runs-dir", str(tmp_path)]) == EXIT_FAILED
    assert "Traceback" not in capsys.readouterr().err


def test_a_full_run_prints_the_summary_and_leaves_the_run_directory(conversion, tmp_path, capsys):
    tools = FakeTools([conversion.snapshot])
    runs = tmp_path / "runs"
    code = run_spec(tools, conversion.spec, GOLDEN_FILE, runs)
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "complete" in out and "Toluene" in out and "运行目录" in out
    run_dir = runs / only_run(runs)
    assert (run_dir / "state.json").is_file() and (run_dir / "trace.jsonl").is_file()
    assert (run_dir / "artifacts" / "plan.json").is_file()


def test_trace_command_prints_the_timeline_of_a_finished_run(conversion, tmp_path, capsys):
    runs = tmp_path / "runs"
    run_spec(FakeTools([conversion.snapshot]), conversion.spec, GOLDEN_FILE, runs)
    capsys.readouterr()
    assert main(["trace", only_run(runs), "--runs-dir", str(runs)]) == EXIT_OK
    out = capsys.readouterr().out
    for state in ("PLAN", "PREFLIGHT", "BUILD_BASIS", "BUILD_FLOWSHEET", "SOLVE", "VERIFY"):
        assert state in out
    assert "complete" in out and "session.connect" in out


def test_trace_command_for_an_unknown_task_says_so(tmp_path, capsys):
    assert main(["trace", "nope", "--runs-dir", str(tmp_path)]) == EXIT_FAILED
    assert "没有找到任务 nope" in capsys.readouterr().err


def test_a_failed_run_prints_the_diagnosis_and_exits_non_zero(conversion, tmp_path, capsys):
    always = {ToolName.BASIS_ENSURE_THERMO: ErrorCode.COMPONENT_NOT_FOUND}
    tools = FakeTools([conversion.snapshot], always=always)
    code = run_spec(tools, conversion.spec, GOLDEN_FILE, tmp_path / "runs")
    captured = capsys.readouterr()
    assert code == EXIT_FAILED
    assert "basis.ensure_thermo" in captured.err and "E_COMPONENT_NOT_FOUND" in captured.err
    assert "Trace：" in captured.err


def test_the_frozen_spec_of_a_run_can_be_rerun_and_has_the_same_hash(conversion, tmp_path):
    runs = tmp_path / "runs"
    run_spec(FakeTools([conversion.snapshot]), conversion.spec, GOLDEN_FILE, runs)
    store = StateStore(runs)
    frozen = store.artifact_path(only_run(runs), ArtifactName.MODEL_SPEC)
    again = load_model_spec(frozen)
    assert spec_hash(again) == spec_hash(conversion.spec)
    assert run_spec(FakeTools([conversion.snapshot]), again, frozen, runs) == EXIT_OK


@pytest.mark.parametrize("arguments", [[], ["run"], ["trace"], ["frobnicate"]])
def test_wrong_usage_is_refused_by_the_argument_parser(arguments, capsys):
    with pytest.raises(SystemExit) as caught:
        main(arguments)
    assert caught.value.code != 0
    assert "Traceback" not in capsys.readouterr().err


def test_a_request_the_system_cannot_build_exits_with_the_unsupported_code(
    conversion, tmp_path, capsys
):
    always = {ToolName.BASIS_ENSURE_REACTION: ErrorCode.UNSUPPORTED}
    tools = FakeTools([conversion.snapshot], always=always)
    assert run_spec(tools, conversion.spec, GOLDEN_FILE, tmp_path / "runs") == EXIT_UNSUPPORTED
    assert "unsupported" in capsys.readouterr().err


def test_output_streams_are_switched_to_utf8_so_chinese_survives_a_redirect(monkeypatch):
    legacy = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    legacy_err = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", legacy)
    monkeypatch.setattr(sys, "stderr", legacy_err)
    _use_utf8_streams()
    assert legacy.encoding == "utf-8" and legacy_err.encoding == "utf-8"
    print("工况 T710：710 °C", file=legacy)
    legacy.flush()
    assert "工况 T710：710 °C" in legacy.buffer.getvalue().decode("utf-8")
