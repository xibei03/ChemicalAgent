# 示例：反应可逆，但转化率是已知条件

## 输入

二氧化硫催化氧化 2SO2 + O2 ⇌ 2SO3，在 450 °C、1.2 atm 下进行。工艺要求 SO2 的单程转化率取 96%，这次不需要考虑动力学。进料 SO2 100 kmol/h，空气 400 kmol/h。请计算出口组成。

## 输出

```json
{
  "features": {
    "is_reaction_process": {"value": true, "evidence": "二氧化硫催化氧化 2SO2 + O2 ⇌ 2SO3"},
    "named_reactor": {"reactor_type": null, "evidence": null},
    "kinetics_given": {"value": false, "evidence": null},
    "dimensions_given": {"value": false, "evidence": null},
    "equipment_form": "unspecified",
    "conversion_data_given": {"value": true, "evidence": "SO2 的单程转化率取 96%"},
    "reaction_defined": {"value": true, "evidence": "2SO2 + O2 ⇌ 2SO3"},
    "black_box_system": {"value": false, "evidence": null},
    "equilibrium_constant_given": {"value": false, "evidence": null},
    "phase": "gas",
    "polymerization": {"value": false, "evidence": null}
  },
  "recommended_type": "conversion",
  "rationale": "原文没有动力学参数，但把 SO2 的单程转化率取 96% 作为已知条件给了出来，按选择逻辑选 Conversion。反应虽然可逆，但用户已经规定了转化率，不需要再用平衡反应器去求；可以提醒核对 96% 没有超过 450 °C 下的平衡极限。",
  "alternatives": [
    {"reactor_type": "equilibrium", "why_not": "反应明确所以能建，但用户已经规定了转化率，优先级低于 Conversion"},
    {"reactor_type": "gibbs", "why_not": "能建，但优先级最低；反应明确，不是黑箱体系"},
    {"reactor_type": "pfr", "why_not": "没有动力学参数，无法建"},
    {"reactor_type": "cstr", "why_not": "没有动力学参数，无法建"}
  ]
}
```
