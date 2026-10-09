# 示例：有动力学参数，釜式

## 输入

环氧乙烷在酸催化下与水反应生成乙二醇：C2H4O + H2O → C2H6O2。液相反应，对环氧乙烷为一级，速率常数 k = 0.8 1/min（60 °C 下），活化能 80 kJ/mol。反应在一台容积 10 m3 的搅拌釜中进行，进料环氧乙烷 2 kmol/h，水大大过量，温度 60 °C，压力 3 bar。请模拟釜出口组成。

## 输出

```json
{
  "features": {
    "is_reaction_process": {"value": true, "evidence": "环氧乙烷在酸催化下与水反应生成乙二醇"},
    "named_reactor": {"reactor_type": null, "evidence": null},
    "kinetics_given": {"value": true, "evidence": "速率常数 k = 0.8 1/min（60 °C 下），活化能 80 kJ/mol"},
    "dimensions_given": {"value": true, "evidence": "容积 10 m3"},
    "equipment_form": "vessel",
    "conversion_data_given": {"value": false, "evidence": null},
    "reaction_defined": {"value": true, "evidence": "C2H4O + H2O → C2H6O2"},
    "black_box_system": {"value": false, "evidence": null},
    "equilibrium_constant_given": {"value": false, "evidence": null},
    "phase": "liquid",
    "polymerization": {"value": false, "evidence": null}
  },
  "recommended_type": "cstr",
  "rationale": "原文给出了速率常数和活化能，有动力学参数，按选择逻辑选动力学反应器；反应在“搅拌釜”里进行，是釜式，所以选 CSTR。设备尺寸（容积 10 m3）也已给出。",
  "alternatives": [
    {"reactor_type": "pfr", "why_not": "同样是动力学反应器，但设备是釜式，不是管式"},
    {"reactor_type": "conversion", "why_not": "没有给出转化率数值，而且有动力学参数时优先选动力学反应器"},
    {"reactor_type": "equilibrium", "why_not": "反应虽然明确，但有动力学参数时优先选动力学反应器"},
    {"reactor_type": "gibbs", "why_not": "反应明确且不是黑箱体系，Gibbs 的优先级更低"}
  ]
}
```
