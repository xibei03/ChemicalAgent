"""任务状态和运行目录：计数、迁移、保存再读回、原子写入。"""

from datetime import datetime
from pathlib import Path

import pytest

from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import (
    RecoveryAction,
    ResultStatus,
    TaskStatus,
    ToolName,
    WorkflowState,
)
from reactor_agent.spec.results import RunResult
from reactor_agent.state.models import CaseSummary, TaskError, TaskState
from reactor_agent.state.store import ArtifactName, StateStore, new_task_id


def make_task(**changes: object) -> TaskState:
    fields = {
        "task_id": "20261009-120000-ab",
        "spec_file": Path("spec.yaml"),
        "spec_hash": "0" * 64,
        "case_names": ("T710", "T600"),
    }
    return TaskState(**{**fields, **changes})


def make_error(code: ErrorCode = ErrorCode.NOT_FOUND) -> TaskError:
    return TaskError(
        state=WorkflowState.BUILD_BASIS,
        tool="basis.ensure_thermo",
        arguments="{}",
        code=code,
        message="没有找到",
        details={"Methane": "没有这个组分"},
        action=RecoveryAction.RETRY,
    )


def summary(name: str, fatal: int = 0) -> CaseSummary:
    return CaseSummary(name=name, fatal_failures=fatal, warning_failures=0, case_file=None)


def test_retries_are_counted_per_position_and_start_over_when_the_position_changes():
    task = make_task()
    task.count_retry()
    task.count_retry()
    assert (task.retries_here(), task.retries_total) == (2, 2)
    task.complete_step(1, ToolName.BASIS_ENSURE_THERMO, ResultStatus.CREATED)
    assert task.retries_here() == 0  # 游标前进，位置变了
    task.count_retry()
    assert (task.retries_here(), task.retries_total) == (1, 3)


def test_a_completed_step_records_the_attempts_it_took():
    task = make_task()
    task.count_retry()
    task.complete_step(1, ToolName.BASIS_ENSURE_THERMO, ResultStatus.CREATED)
    task.complete_step(2, ToolName.BASIS_ENSURE_REACTION, ResultStatus.CREATED)
    assert [(s.number, s.attempts) for s in task.steps] == [(1, 2), (2, 1)]
    assert task.cursor == 2


def test_the_case_name_is_only_known_in_per_case_states():
    task = make_task()
    assert task.current_case_name is None
    task.enter(WorkflowState.SOLVE)
    assert task.current_case_name == "T710"
    task.next_case()
    task.enter(WorkflowState.VERIFY)
    assert task.current_case_name == "T600"
    task.enter(WorkflowState.REPORT)
    assert task.current_case_name is None


def test_rebuilding_resets_the_plan_cursor_the_cases_and_the_retry_counts():
    task = make_task()
    task.set_session("V15", 42)
    task.set_case_file(Path("working-1.hsc"))
    task.complete_step(3, ToolName.BASIS_ENSURE_REACTION, ResultStatus.CREATED)
    task.record_case(summary("T710"))
    task.next_case()
    task.count_retry()
    task.reset_for_rebuild()
    assert (task.cursor, task.case_index, task.steps, task.cases) == (0, 0, (), ())
    assert (task.rebuilds, task.retries_here(), task.retries_total) == (1, 0, 1)
    assert task.session is not None and task.session.case_file is None
    assert task.session.process_id == 42  # 会话还在


def test_recording_a_case_twice_replaces_it_in_place():
    task = make_task()
    task.record_case(summary("T710", fatal=1))
    task.record_case(summary("T600"))
    task.record_case(summary("T710"))
    assert [(c.name, c.fatal_failures) for c in task.cases] == [("T710", 0), ("T600", 0)]


def test_a_failure_report_exists_only_for_a_task_that_did_not_complete():
    task = make_task()
    task.record_error(make_error())
    assert task.failure_report(Path("t.jsonl"), Path("s.json")) is None  # 还在运行
    task.finish(TaskStatus.COMPLETE)
    assert task.failure_report(Path("t.jsonl"), Path("s.json")) is None  # 重试后完成
    failed = make_task()
    failed.record_error(make_error(ErrorCode.COMPONENT_NOT_FOUND))
    failed.finish(TaskStatus.FAILED)
    report = failed.failure_report(Path("t.jsonl"), Path("s.json"))
    assert report is not None
    assert report.code is ErrorCode.COMPONENT_NOT_FOUND
    assert report.details == {"Methane": "没有这个组分"}


def test_saving_then_loading_gives_the_same_state_and_leaves_no_temporary_file(tmp_path):
    store = StateStore(tmp_path)
    task = make_task()
    store.create_run_dir(task.task_id)
    task.set_session("V15", 42)
    task.record_error(make_error())
    task.complete_step(1, ToolName.BASIS_ENSURE_THERMO, ResultStatus.CREATED)
    store.save(task)
    assert store.load(task.task_id) == task
    names = sorted(path.name for path in store.run_dir(task.task_id).iterdir())
    assert names == ["artifacts", "state.json", "work"]


def test_a_failed_write_keeps_the_previous_state_file(tmp_path, monkeypatch):
    store = StateStore(tmp_path)
    task = make_task()
    store.create_run_dir(task.task_id)
    store.save(task)
    task.enter(WorkflowState.PLAN)

    def broken_replace(self: Path, target: Path) -> Path:
        raise OSError("磁盘满了")

    monkeypatch.setattr(Path, "replace", broken_replace)
    with pytest.raises(ReactorAgentError) as caught:
        store.save(task)
    assert caught.value.code is ErrorCode.IO
    monkeypatch.undo()
    assert store.load(task.task_id).current_state is WorkflowState.INIT


def test_loading_a_missing_or_broken_state_file_is_a_domain_error(tmp_path):
    store = StateStore(tmp_path)
    with pytest.raises(ReactorAgentError) as missing:
        store.load("nope")
    assert missing.value.code is ErrorCode.IO
    store.create_run_dir("broken")
    (store.run_dir("broken") / "state.json").write_text('{"task_id": 3}', encoding="utf-8")
    with pytest.raises(ReactorAgentError) as broken:
        store.load("broken")
    assert broken.value.code is ErrorCode.SCHEMA


def test_a_run_directory_is_never_reused(tmp_path):
    store = StateStore(tmp_path)
    store.create_run_dir("same")
    with pytest.raises(ReactorAgentError) as caught:
        store.create_run_dir("same")
    assert caught.value.code is ErrorCode.CONFLICT


def test_a_new_run_gets_another_task_id_when_the_first_one_is_taken(tmp_path, monkeypatch):
    store = StateStore(tmp_path)
    ids = iter(["20261009-120000-aa", "20261009-120000-aa", "20261009-120000-bb"])
    monkeypatch.setattr("reactor_agent.state.store.new_task_id", lambda now: next(ids))
    now = datetime(2026, 10, 9, 12, 0, 0)
    assert store.new_run(now) == "20261009-120000-aa"
    assert store.new_run(now) == "20261009-120000-bb"
    assert store.work_dir("20261009-120000-bb").is_dir()


def test_a_new_run_gives_up_when_every_task_id_is_taken(tmp_path, monkeypatch):
    store = StateStore(tmp_path)
    store.create_run_dir("20261009-120000-aa")
    monkeypatch.setattr("reactor_agent.state.store.new_task_id", lambda now: "20261009-120000-aa")
    with pytest.raises(ReactorAgentError) as caught:
        store.new_run(datetime(2026, 10, 9, 12, 0, 0))
    assert caught.value.code is ErrorCode.IO


def test_recording_a_case_file_before_there_is_a_session_is_a_programming_error():
    with pytest.raises(RuntimeError):
        make_task().set_case_file(Path("case.hsc"))


def test_artifacts_round_trip_through_json(tmp_path):
    store = StateStore(tmp_path)
    store.create_run_dir("t")
    result = RunResult(task_id="t", status=TaskStatus.FAILED, cases=())
    path = store.write_artifact("t", ArtifactName.RESULT, result)
    assert path == tmp_path / "t" / "artifacts" / "result.json"
    assert store.read_artifact("t", ArtifactName.RESULT, RunResult) == result


def test_the_task_id_has_the_plan_format():
    task_id = new_task_id(datetime(2026, 10, 2, 15, 30, 12))
    assert task_id.startswith("20261002-153012-")
    assert len(task_id.rsplit("-", 1)[1]) == 2
