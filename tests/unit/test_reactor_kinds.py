"""三种反应器的差别全在一张表里：类型字符串、可挂的反应类型、已验证的热模式。"""

import pytest

from reactor_agent.backends.hysys_com.reactor_kinds import REACTOR_KINDS, kind_of, reactor_type_of
from reactor_agent.errors import ErrorCode, ReactorAgentError
from reactor_agent.spec.enums import HeatMode, ReactionKind, ReactorType


def test_three_reactor_types_are_supported_and_have_distinct_hysys_names():
    assert set(REACTOR_KINDS) == {
        ReactorType.CONVERSION,
        ReactorType.EQUILIBRIUM,
        ReactorType.GIBBS,
    }
    kinds = REACTOR_KINDS.values()
    assert len({kind.operation_type for kind in kinds}) == 3
    assert len({kind.type_name for kind in kinds}) == 3


@pytest.mark.parametrize("reactor_type", [ReactorType.PFR, ReactorType.CSTR])
def test_pfr_and_cstr_are_unsupported_for_now(reactor_type):
    with pytest.raises(ReactorAgentError) as caught:
        kind_of(reactor_type)
    assert caught.value.code is ErrorCode.UNSUPPORTED


def test_hysys_type_name_maps_back_to_the_reactor_type():
    for reactor_type, kind in REACTOR_KINDS.items():
        assert reactor_type_of(kind.type_name) is reactor_type
    assert reactor_type_of("valveop") is None


def test_each_reactor_takes_only_its_own_kind_of_reaction_and_gibbs_takes_none():
    assert kind_of(ReactorType.CONVERSION).reaction_kind is ReactionKind.CONVERSION
    assert kind_of(ReactorType.EQUILIBRIUM).reaction_kind is ReactionKind.EQUILIBRIUM
    assert kind_of(ReactorType.GIBBS).reaction_kind is None


def test_only_verified_heat_modes_are_offered():
    assert kind_of(ReactorType.EQUILIBRIUM).heat_modes == set(HeatMode)
    for reactor_type in (ReactorType.CONVERSION, ReactorType.GIBBS):
        modes = kind_of(reactor_type).heat_modes
        assert HeatMode.SPECIFIED_DUTY not in modes
        assert {HeatMode.ADIABATIC, HeatMode.SPECIFIED_OUTLET_TEMPERATURE} <= modes
