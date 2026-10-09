"""三份黄金规格的参照值（计划 §17）：独立算出来的，不是 HYSYS 的输出。"""

SPEC_NAMES = ("toluene_conversion", "smr_equilibrium", "slurry_gibbs")
# 计划 §17 的参照值：规格 → 工况 → (出料, 湿基摩尔分率, 容差)
REFERENCES = {
    "toluene_conversion": {
        "base": (
            "Vap",
            {"Toluene": 0.5, "Benzene": 0.25, "p-Xylene": 0.06, "m-Xylene": 0.13, "o-Xylene": 0.06},
            0.001,
        )
    },
    "smr_equilibrium": {
        "T710": (
            "Vap",
            {"Methane": 0.094, "H2O": 0.381, "Hydrogen": 0.411, "CO": 0.047, "CO2": 0.067},
            0.02,
        ),
        "T600": (
            "Vap",
            {"Methane": 0.162, "H2O": 0.499, "Hydrogen": 0.269, "CO": 0.012, "CO2": 0.058},
            0.02,
        ),
    },
    "slurry_gibbs": {"base": ("Vap-2", {"CO": 0.500, "Hydrogen": 0.482}, 0.02)},
}
CO_YIELD_RANGE_PERCENT = (38.0, 42.0)
