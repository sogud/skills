---
name: investment-research
description: Research companies, industries and investment theses, or analyze market sensitivity, correlation, concentration and portfolio stress using attributable evidence and aligned return data. Use for fundamental research, supply-chain questions, thesis reviews or systematic-risk analysis; not for a simple quote, portfolio bookkeeping or trade execution.
---

# Investment Research

一条投资研究流程，按问题选择证据和计算。公司研究检查业务、产业与论点；风险研究检查基准敏感度、共同风险和组合暴露。同一问题可以结合两者，不分独立技能、日常简版或深度版，也不要求用户先选模式。

## 一条工作流程

1. **确定问题与期限。** 确认研究对象、市场、截至日期、判断期限和已有同主题结论，优先复核而非重复建档。风险计算还须明确基准及选择理由、币种和区间。市场问题不索要持仓；组合问题只使用用户提供或宿主已确认的数据和权重，注明确认日期。只有缺项会改变结论时才追问。
2. **取得并核查数据。** 在 AgentSpace 先读工作区根的 `knowledge/Invest/Reference/Agent行情数据工作流.md`，沿用其选源、时效和有限回退规则，只检查本次所需能力。每个重要数字保留原始来源、观察日期或报告期、单位与币种；新闻、社交信号和图表不能代替基本面、合格收益序列或完整市场筛选。其它工作区沿用宿主来源规则，不能声称已通过 AgentSpace 校验。
3. **建立解释并计算。** 公司结论用披露、财务和业务证据；估值比较须有同口径同行，产业链、技术或供需分析按问题扩展。Beta、相关性、集中度或情景计算先读 `resources/data-contract.md` 和 `resources/beta-methods.md`，对合格的日度总回报序列使用 `scripts/analyze.py`，不让模型心算。报告实际样本、区间、回报口径、基准、标准误或置信区间、R²和遗漏数据。多因子或非线性产品不能强塞进单因子脚本。
4. **检验反方与限制。** 分开事实、估算、假设、推断和缺项，检查能推翻核心论点的证据。涉及风险估计时，检查基准与区间敏感性、权重变化、异步市场、残差风险和样本不足。静态权重估计不是账户实际历史业绩，Beta 不是涨跌概率或明日预测；不编造数字、主观概率或来源。
5. **结论与复核。** 回答原问题，给支持证据、主要反方、适用条件、失效条件和复核期限。缺项只限制依赖它的结论；核心证据不足时列出具体缺项，不输出无依据的推荐或暴露值。可检验预测事先记录方向或条件、观察标的、基准、期限及判定方法，保留原判断和错判，不能事后换口径。研究质量、风险估计、方向判断和交易盈亏分开评估；没有基准、成本和足够样本，不声称有稳定 Alpha。

已有授权内的只读查询和本地计算直接执行。新安装、登录、购买或扩大私有访问范围按宿主规则处理；缺工具不自动变成安装任务。本技能不读取券商账户、不交易、不自动对冲。操作建议交给投资总流程结合真实持仓、预算、风险和期限处理，不把研究评级或风险估计直接变成买卖指令。

## 按问题读取资料

- 问题含糊：`references/stages/clarify.md`。
- 证据组织与取数：`references/stages/source-map.md`、`resources/data-rigor.md`；具体字段缺失再读 `resources/source-recipes.md` 对应条目。
- 产业链或瓶颈：`references/stages/chain-trace.md`。
- 论点及反证：`references/stages/thesis-audit.md`。
- 宏观状态：`references/stages/market-regime.md`。
- 风险暴露：`references/stages/factor-exposure.md`。
- 相关与集中：`references/stages/correlation-risk.md`。
- 压力情景：`references/stages/stress-test.md`、`resources/scenario-library.md`。
- 组合综合检查：`references/stages/portfolio-audit.md`。
- 完成交付前：`references/stages/report-quality.md`。

只读相关模块。`resources/research-tool-stack.md`、`resources/data-providers/` 是能力参考，不是每次执行的前置清单；其安装、格式与旧运行建议不覆盖本入口和宿主授权、数据规则。阶段模板仅是需要时的字段参考，不要求每次生成所有文件。

## 可重复运行的风险计算

输入契约和命令见 `resources/data-contract.md`。`scripts/analyze.py` 仅用 Python 标准库，离线读取已准备的 JSON，输出计算及逐项数据限制，不联网、不读账户、不安装依赖。

支持单基准 OLS、HC1 标准误、95% 渐近区间、滚动 Beta、共同区间相关矩阵、显式固定权重组合和单基准情景近似。默认至少 60 个共同回报区间、252 区间滚动窗口；不足时不伪造结果。这些是计算约定，不是策略有效性证明。多因子、自动全市场取数、基金实时估值、风险平价和实盘执行不在此脚本能力内。

## 记录与交付

默认中文 Markdown，正式报告是唯一正文。资料、计算输入和必要复现记录放宿主指定目录；在 AgentSpace 使用 `finance/data/research/<topic>/`，正式研究按根规则进入 `knowledge/Invest/Research/`。持仓和日报仍沿用投资总流程，不新建第二套记录。

用户明确要 HTML 时，才读取 `resources/report-visual-system.md`、`resources/citation-system.md` 以及适合问题的 `templates/report.html` 或 `templates/beta-report.html`。HTML 不是另一套研究流程，不能用可视化掩盖数据缺失。

需要记录过程时使用统一的 `templates/run-log.md`；论点预测按 `templates/thesis-card.md` 记录。复核区分未到期、条件未触发、无法评估、支持与否定，不把未触发计为成功。
