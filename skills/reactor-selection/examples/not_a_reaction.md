# 示例：不是反应过程

## 输入

用水在填料塔里吸收尾气中的氨，气体流量 5000 Nm3/h，含氨 3%，吸收水量 8 m3/h，常温常压，请算塔底氨水浓度和尾气残余氨含量。

## 输出

```json
{
  "features": {
    "is_reaction_process": {"value": false, "evidence": null},
    "named_reactor": {"reactor_type": null, "evidence": null},
    "kinetics_given": {"value": false, "evidence": null},
    "dimensions_given": {"value": false, "evidence": null},
    "equipment_form": "unspecified",
    "conversion_data_given": {"value": false, "evidence": null},
    "reaction_defined": {"value": false, "evidence": null},
    "black_box_system": {"value": false, "evidence": null},
    "equilibrium_constant_given": {"value": false, "evidence": null},
    "phase": "unknown",
    "polymerization": {"value": false, "evidence": null}
  },
  "recommended_type": null,
  "rationale": "要模拟的是填料塔里的气体吸收，是传质分离，不是发生化学反应的过程，不需要选反应器。",
  "alternatives": []
}
```
