"""Case 的创建、打开、保存和关闭：用假的 COM 对象检查 Backend 自己的判断，不需要 HYSYS。"""

from pathlib import Path

import pytest

from reactor_agent.backends.hysys_com.cases import (
    case_path,
    close_case,
    ensure_case,
    normalize_path,
    save_case,
)
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import CaseMode, ResultStatus
from reactor_agent.spec.tool_args import EnsureCaseArgs


class FakeCase:
    """新建时路径在 HYSYS 的当前目录里；SaveAs 写文件并改路径，write=False 模拟静默不写文件。"""

    def __init__(self, name, write=True):
        self.FullName = f"C:\\Windows\\system32\\{name}.hsc"
        self.write, self.calls = write, []

    def SaveAs(self, path):
        self.calls.append(("SaveAs", path))
        if self.write:
            Path(path).write_bytes(b"case")
        self.FullName = path

    def Save(self):
        self.calls.append(("Save", self.FullName))
        Path(self.FullName).write_bytes(b"case again")

    def Close(self):
        self.calls.append(("Close", self.FullName))


class FakeCases:
    def __init__(self, write=True, opened_as=None):
        self.write, self.opened_as, self.added, self.opened = write, opened_as, [], []

    def Add(self, name):
        self.added.append(name)
        return FakeCase(name, self.write)

    def Open(self, path):
        self.opened.append(path)
        case = FakeCase("opened")
        case.FullName = self.opened_as or path
        return case


class FakeApp:
    def __init__(self, **options):
        self.SimulationCases = FakeCases(**options)


def error_of(call):
    with pytest.raises(ReactorAgentError) as caught:
        call()
    return caught.value


def new_args(path):
    return EnsureCaseArgs(path=path, mode=CaseMode.NEW)


def test_new_case_is_saved_to_the_requested_path_immediately(tmp_path):
    app = FakeApp()
    path = tmp_path / "model.hsc"
    ensured = ensure_case(app, None, new_args(path))
    assert ensured.status is ResultStatus.CREATED
    assert app.SimulationCases.added == ["model"]
    assert path.is_file()
    assert case_path(ensured.case).name == "model.hsc"


def test_new_case_never_overwrites_an_existing_file(tmp_path):
    path = tmp_path / "model.hsc"
    path.write_bytes(b"precious")
    app = FakeApp()
    assert error_of(lambda: ensure_case(app, None, new_args(path))).code is ErrorCode.CONFLICT
    assert app.SimulationCases.added == []
    assert path.read_bytes() == b"precious"


def test_saveas_that_silently_writes_nothing_is_detected(tmp_path):
    app = FakeApp(write=False)
    error = error_of(lambda: ensure_case(app, None, new_args(tmp_path / "model.hsc")))
    assert error.code is ErrorCode.IO


def test_open_case_for_the_same_path_is_unchanged_and_other_path_is_a_conflict(tmp_path):
    app = FakeApp()
    active = ensure_case(app, None, new_args(tmp_path / "model.hsc")).case
    again = ensure_case(app, active, new_args(tmp_path / "model.hsc"))
    assert again.status is ResultStatus.UNCHANGED
    assert again.case is active
    assert app.SimulationCases.added == ["model"]
    other = error_of(lambda: ensure_case(app, active, new_args(tmp_path / "other.hsc")))
    assert other.code is ErrorCode.CONFLICT


def test_open_mode_needs_an_existing_file_and_reads_the_path_back(tmp_path):
    missing = EnsureCaseArgs(path=tmp_path / "gone.hsc", mode=CaseMode.OPEN)
    assert error_of(lambda: ensure_case(FakeApp(), None, missing)).code is ErrorCode.IO
    existing = tmp_path / "there.hsc"
    existing.write_bytes(b"case")
    args = EnsureCaseArgs(path=existing, mode=CaseMode.OPEN)
    assert ensure_case(FakeApp(), None, args).status is ResultStatus.UPDATED
    wrong = FakeApp(opened_as="C:\\somewhere\\else.hsc")
    assert error_of(lambda: ensure_case(wrong, None, args)).code is ErrorCode.READBACK_MISMATCH


def test_path_is_validated_before_hysys_is_involved(tmp_path):
    assert error_of(lambda: normalize_path(tmp_path / "no_dir" / "m.hsc")).code is ErrorCode.IO
    assert error_of(lambda: normalize_path(tmp_path / "a<b>.hsc")).code is ErrorCode.IO
    assert normalize_path(tmp_path / "m.hsc") == tmp_path.resolve() / "m.hsc"


def test_save_without_a_path_rewrites_the_current_file(tmp_path):
    case = ensure_case(FakeApp(), None, new_args(tmp_path / "model.hsc")).case
    path, size = save_case(case, None)
    assert path == tmp_path / "model.hsc"
    assert size == len(b"case again")
    assert case.calls[-1][0] == "Save"


def test_save_to_a_new_path_changes_the_case_path(tmp_path):
    case = ensure_case(FakeApp(), None, new_args(tmp_path / "model.hsc")).case
    path, size = save_case(case, tmp_path / "copy.hsc")
    assert path == tmp_path.resolve() / "copy.hsc"
    assert size > 0
    assert case_path(case).name == "copy.hsc"


def test_close_returns_the_path_and_can_save_first(tmp_path):
    case = ensure_case(FakeApp(), None, new_args(tmp_path / "model.hsc")).case
    assert close_case(case, save=True) == tmp_path.resolve() / "model.hsc"
    assert [name for name, _ in case.calls][-2:] == ["Save", "Close"]
