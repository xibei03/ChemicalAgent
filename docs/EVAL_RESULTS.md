# 选型评测结果

由 `evals/run_evals.py` 生成，不要手工修改。

- 模型：qwen3.8-max
- Skill：reactor-selection 0.1.0（内容哈希 8e0109a6cd81）
- 提交：ec882ff，有未提交的改动
- 时间：2026-10-09 15:05:49 +0000
- 运行目录：runs/evals-20261009-150017

## 汇总：**未通过**

| 指标 | 结果 | 门槛 |
|---|---|---|
| 三个原文场景的类型（各 5 次） | 10 / 15 | 全部正确 |
| 其余用例 | 错 1 / 26 个 | 至多错 1 个 |
| 输出经校验合法的比例（含一次重问） | 100.0% | 100% |
| 最终结论的类型准确率（全部运行） | 85.4% | 记录 |
| LLM 第一次推荐的类型准确率 | 85.4% | 记录 |
| 规则用第一次抽的特征推出的类型准确率 | 85.4% | 记录 |
| 需要重问的运行占比 | 0.0% | 记录 |
| 重复运行的一致性 | 3 / 3 个用例结论相同 | 记录 |
| 关键特征准确率 | 93.6% | 记录，不设门槛 |
| 用量 | 41 次运行，219008 tokens，331 秒 | 记录 |

决定方式的分布：一致 41

## 逐个用例

| 用例 | 期望 | 每次运行的结论 | 决定方式 | 关键特征 | 结果 |
|---|---|---|---|---|---|
| L1-S1 | Equilibrium | ✗Gibbs ✗Gibbs ✗Gibbs ✗Gibbs ✗Gibbs | 一致×5 | 16/25 | **未通过** |
| L1-S2 | Conversion | ✓Conversion ✓Conversion ✓Conversion ✓Conversion ✓Conversion | 一致×5 | 25/25 | 通过 |
| L1-S3 | Gibbs | ✓Gibbs ✓Gibbs ✓Gibbs ✓Gibbs ✓Gibbs | 一致×5 | 25/25 | 通过 |
| L1-A1 | Gibbs | ✓Gibbs | 一致×1 | 3/3 | 通过 |
| L1-A2 | Equilibrium | ✓Equilibrium | 一致×1 | 5/5 | 通过 |
| L1-C1 | Conversion | ✓Conversion | 一致×1 | 2/2 | 通过 |
| L1-C2 | Conversion | ✓Conversion | 一致×1 | 2/2 | 通过 |
| L1-C4 | Conversion | ✓Conversion | 一致×1 | 3/3 | 通过 |
| L1-E1 | Equilibrium | ✓Equilibrium | 一致×1 | 5/5 | 通过 |
| L1-E2 | Equilibrium | ✓Equilibrium | 一致×1 | 4/4 | 通过 |
| L1-E3 | Equilibrium | ✓Equilibrium | 一致×1 | 2/2 | 通过 |
| L1-E4 | Gibbs | ✓Gibbs | 一致×1 | 2/2 | 通过 |
| L1-G1 | Gibbs | ✓Gibbs | 一致×1 | 4/4 | 通过 |
| L1-G2 | Gibbs | ✓Gibbs | 一致×1 | 2/2 | 通过 |
| L1-G3 | Gibbs | ✓Gibbs | 一致×1 | 3/3 | 通过 |
| L1-K1 | PFR | ✓PFR | 一致×1 | 4/4 | 通过 |
| L1-K1b | PFR | ✓PFR | 一致×1 | 4/4 | 通过 |
| L1-K1c | PFR | ✓PFR | 一致×1 | 2/2 | 通过 |
| L1-K2 | CSTR | ✓CSTR | 一致×1 | 4/4 | 通过 |
| L1-K2b | CSTR | ✓CSTR | 一致×1 | 4/4 | 通过 |
| L1-K3 | Conversion | ✓Conversion | 一致×1 | 4/4 | 通过 |
| L1-N1 | Conversion | ✓Conversion | 一致×1 | 3/3 | 通过 |
| L1-N2 | Gibbs | ✓Gibbs | 一致×1 | 2/2 | 通过 |
| L1-N3 | CSTR | ✓CSTR | 一致×1 | 3/3 | 通过 |
| L1-S1b | Equilibrium | ✗Gibbs | 一致×1 | 4/5 | **未通过** |
| L1-S2b | Conversion | ✓Conversion | 一致×1 | 4/4 | 通过 |
| L1-S3b | Gibbs | ✓Gibbs | 一致×1 | 3/3 | 通过 |
| L1-X5 | 无 | ✓无 | 一致×1 | 1/1 | 通过 |
| L1-X6 | 无 | ✓无 | 一致×1 | 1/1 | 通过 |

## 错误的运行

### L1-S1（第 1 次）
- 期望 Equilibrium，得到 Gibbs
- LLM 第一次推荐 Gibbs，最终推荐 Gibbs
- 决定方式：一致
- 规则：能建的类型：Gibbs。不能建的类型：Conversion（缺：给出了转化率、收率或选择性的数值）、Equilibrium（缺：反应已明确）、PFR（缺：给出了动力学参数）、CSTR（缺：给出了动力学参数）。
- 规则：第二层的 5 条都不满足，选 Gibbs。
- 特征 reaction_defined：期望 True，得到 False
### L1-S1（第 2 次）
- 期望 Equilibrium，得到 Gibbs
- LLM 第一次推荐 Gibbs，最终推荐 Gibbs
- 决定方式：一致
- 规则：能建的类型：Gibbs。不能建的类型：Conversion（缺：给出了转化率、收率或选择性的数值）、Equilibrium（缺：反应已明确）、PFR（缺：给出了动力学参数）、CSTR（缺：给出了动力学参数）。
- 规则：命中第二层第 4 条：黑箱类体系，产物分布由热力学平衡决定，选 Gibbs。
- 特征 black_box_system：期望 False，得到 True
- 特征 reaction_defined：期望 True，得到 False
### L1-S1（第 3 次）
- 期望 Equilibrium，得到 Gibbs
- LLM 第一次推荐 Gibbs，最终推荐 Gibbs
- 决定方式：一致
- 规则：能建的类型：Gibbs。不能建的类型：Conversion（缺：给出了转化率、收率或选择性的数值）、Equilibrium（缺：反应已明确）、PFR（缺：给出了动力学参数）、CSTR（缺：给出了动力学参数）。
- 规则：命中第二层第 4 条：黑箱类体系，产物分布由热力学平衡决定，选 Gibbs。
- 特征 black_box_system：期望 False，得到 True
- 特征 reaction_defined：期望 True，得到 False
### L1-S1（第 4 次）
- 期望 Equilibrium，得到 Gibbs
- LLM 第一次推荐 Gibbs，最终推荐 Gibbs
- 决定方式：一致
- 规则：能建的类型：Gibbs。不能建的类型：Conversion（缺：给出了转化率、收率或选择性的数值）、Equilibrium（缺：反应已明确）、PFR（缺：给出了动力学参数）、CSTR（缺：给出了动力学参数）。
- 规则：命中第二层第 4 条：黑箱类体系，产物分布由热力学平衡决定，选 Gibbs。
- 特征 black_box_system：期望 False，得到 True
- 特征 reaction_defined：期望 True，得到 False
### L1-S1（第 5 次）
- 期望 Equilibrium，得到 Gibbs
- LLM 第一次推荐 Gibbs，最终推荐 Gibbs
- 决定方式：一致
- 规则：能建的类型：Gibbs。不能建的类型：Conversion（缺：给出了转化率、收率或选择性的数值）、Equilibrium（缺：反应已明确）、PFR（缺：给出了动力学参数）、CSTR（缺：给出了动力学参数）。
- 规则：命中第二层第 4 条：黑箱类体系，产物分布由热力学平衡决定，选 Gibbs。
- 特征 black_box_system：期望 False，得到 True
- 特征 reaction_defined：期望 True，得到 False
### L1-S1b（第 1 次）
- 期望 Equilibrium，得到 Gibbs
- LLM 第一次推荐 Gibbs，最终推荐 Gibbs
- 决定方式：一致
- 规则：能建的类型：Gibbs。不能建的类型：Conversion（缺：给出了转化率、收率或选择性的数值）、Equilibrium（缺：反应已明确）、PFR（缺：给出了动力学参数）、CSTR（缺：给出了动力学参数）。
- 规则：第二层的 5 条都不满足，选 Gibbs。
- 特征 reaction_defined：期望 True，得到 False
