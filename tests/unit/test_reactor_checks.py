"""反应器创建前的检查：反应集的类型必须与反应器匹配，否则 HYSYS 会弹模态对话框。

check_reaction_set 通过 reaction_set_kinds 查反应集成员的类型；这里把查询换成固定的答案，
只检查判断本身，不需要 HYSYS。
"""

import pytest

from reactor_agent.backends.hysys_com import reactors
from reactor_agent.backends.hysys_com.reactor_kinds import kind_of
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import HeatMode, ReactionKind, ReactorType
from reactor_agent.spec.tool_args import EnsureReactorArgs


def reactor_args(reactor_type, reaction_set):
    return EnsureReactorArgs(
        name="R-1",
        reactor_type=reactor_type,
        feeds=("Feed",),
        vapour_product="Vap",
        liquid_product="Liq",
        reaction_set=reaction_set,
        heat_mode=HeatMode.ADIABATIC,
    )


def check(monkeypatch, reactor_type, reaction_set, kinds):
    monkeypatch.setattr(reactors, "reaction_set_kinds", lambda _case, _name: kinds)
    args = reactor_args(reactor_type, reaction_set)
    reactors.check_reaction_set(None, kind_of(reactor_type), args)


def error_of(monkeypatch, reactor_type, reaction_set, kinds):
    with pytest.raises(ReactorAgentError) as caught:
        check(monkeypatch, reactor_type, reaction_set, kinds)
    return caught.value


@pytest.mark.parametrize(
    ("reactor_type", "kind"),
    [
        (ReactorType.CONVERSION, ReactionKind.CONVERSION),
        (ReactorType.EQUILIBRIUM, ReactionKind.EQUILIBRIUM),
    ],
)
def test_reaction_set_of_the_matching_kind_is_accepted(monkeypatch, reactor_type, kind):
    check(monkeypatch, reactor_type, "RxnSet-1", frozenset({kind}))


def test_gibbs_reactor_in_free_energy_mode_accepts_no_reaction_set(monkeypatch):
    check(monkeypatch, ReactorType.GIBBS, None, None)
    error = error_of(monkeypatch, ReactorType.GIBBS, "RxnSet-1", frozenset())
    assert error.code is ErrorCode.SET_INCOMPATIBLE


@pytest.mark.parametrize("reactor_type", [ReactorType.CONVERSION, ReactorType.EQUILIBRIUM])
def test_conversion_and_equilibrium_reactors_need_a_reaction_set(monkeypatch, reactor_type):
    error = error_of(monkeypatch, reactor_type, None, None)
    assert error.code is ErrorCode.SET_INCOMPATIBLE


def test_reaction_set_of_the_wrong_kind_is_rejected_before_hysys_pops_up_a_dialog(monkeypatch):
    error = error_of(
        monkeypatch, ReactorType.CONVERSION, "RxnSet-1", frozenset({ReactionKind.EQUILIBRIUM})
    )
    assert error.code is ErrorCode.SET_INCOMPATIBLE
    assert "equilibrium" in error.message


def test_reaction_set_mixing_kinds_or_empty_is_rejected(monkeypatch):
    mixed = frozenset({ReactionKind.CONVERSION, ReactionKind.EQUILIBRIUM})
    for kinds in (mixed, frozenset()):
        error = error_of(monkeypatch, ReactorType.CONVERSION, "RxnSet-1", kinds)
        assert error.code is ErrorCode.SET_INCOMPATIBLE


def test_reaction_set_that_does_not_exist_yet_is_not_found(monkeypatch):
    error = error_of(monkeypatch, ReactorType.EQUILIBRIUM, "RxnSet-1", None)
    assert error.code is ErrorCode.NOT_FOUND
