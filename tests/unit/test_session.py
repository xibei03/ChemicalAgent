"""连接 HYSYS：进程号、是否复用、版本检查和结束实例。用假的应用对象和假的进程清单。"""

import pytest

from reactor_agent.backends.hysys_com import session
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import ConnectMode

VERSION_15 = "Aspen HYSYS Version 15 (41.0)"


class FakeApp:
    def __init__(self, version=VERSION_15):
        self.Version, self.Visible, self.quit_calls = version, None, 0

    def Quit(self):
        self.quit_calls += 1


class FakeHysys:
    """假的 HYSYS：running 是当前的进程清单，连接（Dispatch）之后 launched 里的进程出现。"""

    def __init__(self):
        self.running, self.launched = frozenset({100}), frozenset()
        self.progids, self.killed, self.app = [], [], FakeApp()

    def running_process_ids(self):
        return self.running

    def dispatch(self, progid):
        self.progids.append(progid)
        self.running = self.running | self.launched
        return self.app


@pytest.fixture
def hysys(monkeypatch):
    fake = FakeHysys()
    monkeypatch.setattr(session, "running_process_ids", fake.running_process_ids)
    monkeypatch.setattr(session.gencache, "EnsureDispatch", fake.dispatch)
    monkeypatch.setattr(session, "_kill", fake.killed.append)
    monkeypatch.setattr(session, "QUIT_WAIT_S", 0.2)
    monkeypatch.setattr(session, "QUIT_POLL_S", 0.05)
    return fake


def test_launch_opens_a_new_instance_and_takes_the_new_process_as_its_own(hysys):
    hysys.launched = frozenset({200})
    connected = session.connect(ConnectMode.LAUNCH, visible=False)
    assert connected.process_id == 200
    assert connected.reused_instance is False
    assert connected.version == VERSION_15
    assert hysys.progids == [session.NEW_INSTANCE_PROGID]
    assert hysys.app.Visible is False


def test_launch_without_exactly_one_new_process_fails_and_quits_the_instance(hysys):
    with pytest.raises(ReactorAgentError) as caught:
        session.connect(ConnectMode.LAUNCH, visible=True)
    assert caught.value.code is ErrorCode.COM_UNAVAILABLE
    assert hysys.app.quit_calls == 1


def test_attach_to_a_running_instance_is_a_reuse_that_must_not_be_ended(hysys):
    connected = session.connect(ConnectMode.ATTACH, visible=True)
    assert (connected.process_id, connected.reused_instance) == (100, True)
    assert hysys.progids == [session.SHARED_INSTANCE_PROGID]
    session.shutdown(connected)
    assert hysys.app.quit_calls == 0
    assert hysys.killed == []


def test_attach_with_several_running_instances_cannot_tell_which_one(hysys):
    hysys.running = frozenset({100, 101})
    connected = session.connect(ConnectMode.ATTACH, visible=True)
    assert (connected.process_id, connected.reused_instance) == (None, True)


def test_attach_that_has_to_start_hysys_owns_the_new_process(hysys):
    hysys.launched = frozenset({300})
    connected = session.connect(ConnectMode.ATTACH, visible=True)
    assert (connected.process_id, connected.reused_instance) == (300, False)


def test_other_versions_are_refused_and_the_instance_started_for_them_is_ended(hysys):
    hysys.launched = frozenset({200})
    hysys.app = FakeApp(version="Aspen HYSYS Version 14 (40.0)")
    with pytest.raises(ReactorAgentError) as caught:
        session.connect(ConnectMode.LAUNCH, visible=True)
    assert caught.value.code is ErrorCode.VERSION
    assert hysys.app.quit_calls == 1


def test_shutdown_quits_normally_and_does_not_kill_a_process_that_is_gone(hysys):
    hysys.launched = frozenset({200})
    connected = session.connect(ConnectMode.LAUNCH, visible=True)
    hysys.running = frozenset({100})
    session.shutdown(connected)
    assert hysys.app.quit_calls == 1
    assert hysys.killed == []


def test_shutdown_kills_the_process_by_id_when_quit_does_not_end_it(hysys):
    hysys.launched = frozenset({200})
    connected = session.connect(ConnectMode.LAUNCH, visible=True)
    session.shutdown(connected)
    assert hysys.killed == [200]
