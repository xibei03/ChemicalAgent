"""Recipe 注册表：反应器类型 → 把规格编译成建模计划的 Recipe。

新增一种反应器就是写一个实现 ReactorRecipe 的类并登记在这里；其余代码不按反应器类型分支。
"""

from collections.abc import Mapping
from types import MappingProxyType

from reactor_agent.recipes.base import ReactorRecipe
from reactor_agent.recipes.conversion import ConversionRecipe
from reactor_agent.recipes.equilibrium import EquilibriumRecipe
from reactor_agent.recipes.gibbs import GibbsRecipe
from reactor_agent.spec.enums import ReactorType

RECIPES: Mapping[ReactorType, ReactorRecipe] = MappingProxyType(
    {
        ReactorType.CONVERSION: ConversionRecipe(),
        ReactorType.EQUILIBRIUM: EquilibriumRecipe(),
        ReactorType.GIBBS: GibbsRecipe(),
    }
)


def recipe_for(reactor_type: ReactorType) -> ReactorRecipe | None:
    """反应器类型对应的 Recipe；还没有 Recipe 的类型（PFR、CSTR）是 None，由调用方决定怎么办。"""
    return RECIPES.get(reactor_type)
