# 示例：反应用文字说清，要求计算转化率

## 输入

乙苯在催化剂上脱氢制苯乙烯，温度 600 °C，压力 1.2 bar，进料乙苯 50 kmol/h，用氮气稀释，氮气与乙苯的摩尔比为 5:1。体系里有两个反应：乙苯脱氢生成苯乙烯和氢气；乙苯脱乙基生成苯和乙烯。请算出乙苯能达到的最大转化率和出口组成。

## 输出

```json
{
  "features": {
    "is_reaction_process": {"value": true, "evidence": "乙苯在催化剂上脱氢制苯乙烯"},
    "named_reactor": {"reactor_type": null, "evidence": null},
    "kinetics_given": {"value": false, "evidence": null},
    "dimensions_given": {"value": false, "evidence": null},
    "equipment_form": "unspecified",
    "conversion_data_given": {"value": false, "evidence": null},
    "reaction_defined": {"value": true, "evidence": "体系里有两个反应：乙苯脱氢生成苯乙烯和氢气；乙苯脱乙基生成苯和乙烯"},
    "black_box_system": {"value": false, "evidence": null},
    "equilibrium_constant_given": {"value": false, "evidence": null},
    "phase": "gas",
    "polymerization": {"value": false, "evidence": null}
  },
  "recommended_type": "equilibrium",
  "rationale": "原文列出了两个反应，反应物和产物都用文字说清了（没有写化学方程式也算说清），也没有要求考虑别的反应，所以反应已明确；没有动力学参数。“最大转化率”和“出口组成”是要求算出来的，不是已知条件，也不是产物未知。反应靠催化剂实现、产物种类确定，温度高也不是黑箱。反应明确、受热力学平衡控制，按选择逻辑选 Equilibrium。",
  "alternatives": [
    {"reactor_type": "conversion", "why_not": "要求计算的转化率是待求量，原文没有给出转化率数值"},
    {"reactor_type": "gibbs", "why_not": "能建，但反应已经明确，不是黑箱体系，优先级更低"},
    {"reactor_type": "pfr", "why_not": "没有动力学参数，无法建"},
    {"reactor_type": "cstr", "why_not": "没有动力学参数，无法建"}
  ]
}
```
