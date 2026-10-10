# 选型评测结果

由 `evals/run_evals.py` 生成，不要手工修改。

- 模型：qwen3.8-max
- Skill：reactor-selection 0.1.1（内容哈希 6711ecbab3ef）
- 提交：f1bf10d，有未提交的改动
- 时间：2026-10-10 05:49:41 +0000
- 运行目录：runs/evals-20261010-053752

## 汇总：**通过**

| 指标 | 结果 | 门槛 |
|---|---|---|
| 三个原文场景的类型（各 5 次） | 15 / 15 | 全部正确 |
| 其余用例 | 错 0 / 31 个 | 至多错 1 个 |
| 输出经校验合法的比例（含一次重问） | 100.0% | 100% |
| 最终结论的类型准确率（全部运行） | 100.0% | 记录 |
| LLM 第一次推荐的类型准确率 | 100.0% | 记录 |
| 规则用第一次抽的特征推出的类型准确率 | 100.0% | 记录 |
| 需要重问的运行占比 | 4.3% | 记录 |
| 重复运行的一致性 | 3 / 3 个用例结论相同 | 记录 |
| 关键特征准确率 | 100.0% | 记录，不设门槛 |
| 用量 | 46 次运行，432262 tokens，707 秒 | 记录 |

决定方式的分布：一致 44、重问后一致 2

## 逐个用例

| 用例 | 期望 | 每次运行的结论 | 决定方式 | 关键特征 | 结果 |
|---|---|---|---|---|---|
| L1-S1 | Equilibrium | ✓Equilibrium ✓Equilibrium ✓Equilibrium ✓Equilibrium ✓Equilibrium | 一致×5 | 25/25 | 通过 |
| L1-S2 | Conversion | ✓Conversion ✓Conversion ✓Conversion ✓Conversion ✓Conversion | 一致×3、重问后一致×2 | 25/25 | 通过 |
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
| L1-X1 | Conversion | ✓Conversion | 一致×1 | 1/1 | 通过 |
| L1-X1b | Conversion | ✓Conversion | 一致×1 | 1/1 | 通过 |
| L1-X2 | Conversion | ✓Conversion | 一致×1 | 1/1 | 通过 |
| L1-X3 | Conversion | ✓Conversion | 一致×1 | 1/1 | 通过 |
| L1-X4 | Conversion | ✓Conversion | 一致×1 | 1/1 | 通过 |
| L1-X5 | 无 | ✓无 | 一致×1 | 1/1 | 通过 |
| L1-X6 | 无 | ✓无 | 一致×1 | 1/1 | 通过 |

## 规格评测：**通过**

| 指标 | 结果 | 门槛 |
|---|---|---|
| 三个原文场景的期望参数正确率 | 210 / 210（100.0%） | ≥ 95% |
| 经不超过 2 轮重写后规格合法的比例（三个原文场景） | 15 / 15 | 100% |
| 病态输入 | 通过 5 / 5 个 | 全部通过 |

| 用例 | 运行 | 规格合法 | 期望参数 | 假设登记 | 病态输入 | 重写轮数 |
|---|---|---|---|---|---|---|
| L1-S1 | 5 | 5/5 | 95/95 | 5/5 | — | 0/0/0/0/0 |
| L1-S2 | 5 | 5/5 | 65/65 | 5/5 | — | 0/0/0/0/0 |
| L1-S3 | 5 | 5/5 | 50/50 | 5/5 | — | 0/0/0/0/0 |
| L1-S1b | 1 | 1/1 | 19/19 | 1/1 | — | 0 |
| L1-S2b | 1 | 1/1 | 13/13 | 1/1 | — | 0 |
| L1-S3b | 1 | 1/1 | 9/9 | 1/1 | — | 0 |
| L1-X1 | 1 | 0/1 | — | — | 1/1 | 0 |
| L1-X1b | 1 | 0/1 | — | — | 1/1 | 0 |
| L1-X2 | 1 | 0/1 | — | — | 1/1 | 2 |
| L1-X3 | 1 | 0/1 | — | — | 1/1 | 2 |
| L1-X4 | 1 | 0/1 | — | — | 1/1 | 2 |
