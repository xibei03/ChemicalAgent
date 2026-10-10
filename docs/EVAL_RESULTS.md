# 选型评测结果

由 `evals/run_evals.py` 生成，不要手工修改。

- 模型：qwen3.8-max
- Skill：reactor-selection 0.1.1（内容哈希 6711ecbab3ef）
- 提交：8b95ab4
- 时间：2026-10-10 00:36:44 +0000
- 运行目录：runs/evals-20261010-003006

## 汇总：**通过**

| 指标 | 结果 | 门槛 |
|---|---|---|
| 三个原文场景的类型（各 5 次） | 15 / 15 | 全部正确 |
| 其余用例 | 错 0 / 26 个 | 至多错 1 个 |
| 输出经校验合法的比例（含一次重问） | 100.0% | 100% |
| 最终结论的类型准确率（全部运行） | 100.0% | 记录 |
| LLM 第一次推荐的类型准确率 | 100.0% | 记录 |
| 规则用第一次抽的特征推出的类型准确率 | 100.0% | 记录 |
| 需要重问的运行占比 | 9.8% | 记录 |
| 重复运行的一致性 | 3 / 3 个用例结论相同 | 记录 |
| 关键特征准确率 | 100.0% | 记录，不设门槛 |
| 用量 | 41 次运行，263296 tokens，397 秒 | 记录 |

决定方式的分布：一致 37、重问后一致 4

## 逐个用例

| 用例 | 期望 | 每次运行的结论 | 决定方式 | 关键特征 | 结果 |
|---|---|---|---|---|---|
| L1-S1 | Equilibrium | ✓Equilibrium ✓Equilibrium ✓Equilibrium ✓Equilibrium ✓Equilibrium | 一致×5 | 25/25 | 通过 |
| L1-S2 | Conversion | ✓Conversion ✓Conversion ✓Conversion ✓Conversion ✓Conversion | 重问后一致×4、一致×1 | 25/25 | 通过 |
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
| L1-S1b | Equilibrium | ✓Equilibrium | 一致×1 | 5/5 | 通过 |
| L1-S2b | Conversion | ✓Conversion | 一致×1 | 4/4 | 通过 |
| L1-S3b | Gibbs | ✓Gibbs | 一致×1 | 3/3 | 通过 |
| L1-X5 | 无 | ✓无 | 一致×1 | 1/1 | 通过 |
| L1-X6 | 无 | ✓无 | 一致×1 | 1/1 | 通过 |
