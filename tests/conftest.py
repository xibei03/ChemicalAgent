"""单元测试共用的 fixture：三个场景各有一份“正确的”快照，下一阶段的执行器测试也用它们。"""

import pytest

from builders import Scenario, conversion_scenario, equilibrium_scenario, gasification_scenario

SCENARIOS = {
    "conversion": conversion_scenario,
    "equilibrium": equilibrium_scenario,
    "gasification": gasification_scenario,
}


@pytest.fixture
def conversion() -> Scenario:
    return conversion_scenario()


@pytest.fixture
def equilibrium() -> Scenario:
    return equilibrium_scenario()


@pytest.fixture
def gasification() -> Scenario:
    return gasification_scenario()


@pytest.fixture(params=sorted(SCENARIOS))
def scenario(request: pytest.FixtureRequest) -> Scenario:
    """逐个场景运行同一个测试：每个检查在三种反应器上都应该给出同样的结论。"""
    return SCENARIOS[request.param]()
