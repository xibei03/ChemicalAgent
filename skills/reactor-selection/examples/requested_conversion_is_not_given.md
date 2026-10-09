# 示例：要求计算转化率，不是已知条件

## 输入

乙苯催化脱氢制苯乙烯 C8H10 ⇌ C8H8 + H2，600 °C、1.2 bar，乙苯与水蒸气摩尔比 1:9，乙苯进料 50 kmol/h。请算出乙苯能达到的最大转化率和出口组成。

## 输出

```json
{
  "features": {
    "is_reaction_process": {"value": true, "evidence": "乙苯催化脱氢制苯乙烯 C8H10 ⇌ C8H8 + H2"},
    "named_reactor": {"reactor_type": null, "evidence": null},
    "kinetics_given": {"value": false, "evidence": null},
    "dimensions_given": {"value": false, "evidence": null},
    "equipment_form": "unspecified",
    "conversion_data_given": {"value": false, "evidence": null},
    "reaction_defined": {"value": true, "evidence": "C8H10 ⇌ C8H8 + H2"},
    "black_box_system": {"value": false, "evidence": null},
    "equilibrium_constant_given": {"value": false, "evidence": null},
    "phase": "gas",
    "polymerization": {"value": false, "evidence": null}
  },
  "recommended_type": "equilibrium",
  "rationale": "原文只写了一个明确的可逆反应，没有动力学参数。“最大转化率”是要求算出来的待求量，不是已知条件，所以没有可用的转化率数值。反应明确、受热力学平衡控制，按选择逻辑选 Equilibrium。",
  "alternatives": [
    {"reactor_type": "conversion", "why_not": "要求计算的转化率是待求量，原文没有给出转化率数值"},
    {"reactor_type": "gibbs", "why_not": "能建，但反应已经明确，不是黑箱体系，优先级更低"},
    {"reactor_type": "pfr", "why_not": "没有动力学参数，无法建"},
    {"reactor_type": "cstr", "why_not": "没有动力学参数，无法建"}
  ]
}
```
