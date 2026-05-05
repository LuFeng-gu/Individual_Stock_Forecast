# 基本面分析模块设计

日期：2026-05-04

## 目标

只升级个股预测 Agent 中的基本面分析部分，使它能够满足课程展示要求：基于上市公司财务报表读取或推导核心基本面指标，再把结构化证据传给现有 LLM prompt 进行解读。

本设计不修改技术面、资金面、情绪面、路由、融合或最终报告模块。

## 当前状态

当前 `graph/nodes.py` 中已经有 `fundamental_analysis_node`，它可以接入现有 LangGraph 工作流，并把结果写入 `AgentState` 的 `fundamental_evidence` 字段。

但当前基本面输入数据过薄，只包含：

- 行业
- 总市值
- 动态 PE
- PB
- 换手率

现有 prompt 虽然要求分析 ROE、盈利能力、成长性、债务和现金流，但节点并没有真正提供这些数据。这会导致 LLM 根据常识泛化，而不是基于财报数据进行分析。

## 范围

本次范围包括：

- 在 `graph/nodes.py` 中新增基本面专用数据辅助函数。
- 尽可能通过 akshare 获取利润表、资产负债表、现金流量表相关数据。
- 用 Python 计算一组适合课程展示的核心基本面指标。
- 将计算结果格式化后传入 `fundamental_user.md`。
- 收紧基本面 prompt，要求 LLM 只解读输入数据，不编造缺失财务信息。
- 增加基本面指标计算和节点行为的聚焦测试。

本次范围不包括：

- 技术指标，例如 MA、MACD、RSI。
- 资金流向分析。
- 情绪面分析。
- 因子路由逻辑。
- 跨因子融合逻辑。
- 前端页面或可视化看板。
- 复杂因子模型或机器学习预测。

## 指标清单

课程展示版使用以下基本面指标。

| 类别 | 指标 | 公式或来源 |
| --- | --- | --- |
| 估值 | PE 市盈率 | `总市值 / 归母净利润`，akshare 现成 PE 作为兜底 |
| 估值 | PB 市净率 | `总市值 / 归母净资产`，akshare 现成 PB 作为兜底 |
| 盈利能力 | ROE 净资产收益率 | `归母净利润 / 平均归母净资产` |
| 盈利能力 | 毛利率 | `(营业收入 - 营业成本) / 营业收入` |
| 盈利能力 | 净利率 | `净利润 / 营业收入` |
| 成长性 | 营收同比 | `本期营业收入 / 上年同期营业收入 - 1` |
| 成长性 | 净利润同比 | `本期净利润 / 上年同期净利润 - 1` |
| 财务安全 | 资产负债率 | `总负债 / 总资产` |
| 现金流质量 | 经营现金流/净利润 | `经营现金流净额 / 净利润` |

这些指标覆盖课程 slides 中强调的 PE、PB、ROE，同时补充盈利能力、成长性、偿债安全和利润质量。

## 数据流

基本面节点保持现有图结构契约不变：

```text
AgentState.user_intent
→ fundamental_analysis_node
→ 基本面数据辅助函数
→ Python 指标计算
→ 格式化 fundamental_data
→ planner.generate(...)
→ FactorEvidence
→ AgentState.fundamental_evidence
```

建议新增的函数边界：

```python
_fetch_financial_reports(stock_code) -> dict
_fetch_fundamental_snapshot(stock_code) -> dict
_calculate_fundamental_metrics(reports, valuation, basic) -> dict
_format_fundamental_metrics(metrics) -> str
```

其中：

- `_fetch_financial_reports` 负责通过 akshare 获取财报相关数据。
- `_fetch_fundamental_snapshot` 负责获取行情侧或 akshare 已整理的估值摘要，用作兜底。
- `_calculate_fundamental_metrics` 负责纯指标计算，应尽量便于单元测试。
- `_format_fundamental_metrics` 负责把指标组织成 LLM 可读的分组文本。

## 数据兜底规则

基本面模块应优先使用财报推导值。

1. 如果财报字段完整，则用 Python 直接计算指标。
2. 如果某个财报字段缺失，但 akshare 提供等价摘要指标，则使用摘要指标兜底。
3. 如果两个来源都无法提供足够数据，则该指标返回 `N/A`，并写入数据质量说明。
4. 缺失字段不能导致节点崩溃。
5. prompt 必须要求 LLM 明确说明缺失值，不允许猜测。

这样既能体现“指标来自财报三张表”的课程要求，也能保证课堂演示时足够稳定。

## Prompt 契约

传给 `fundamental_user.md` 的 `fundamental_data` 从短 PE/PB 文本升级为分组结构：

```text
【估值】
PE: ...
PB: ...

【盈利能力】
ROE: ...
毛利率: ...
净利率: ...

【成长性】
营收同比: ...
净利润同比: ...

【财务安全】
资产负债率: ...

【现金流质量】
经营现金流/净利润: ...

【数据质量】
缺失字段: ...
数据来源: 利润表、资产负债表、现金流量表、行情数据
```

输出仍保持当前 `FactorEvidence` JSON 结构：

```json
{
  "factor_name": "fundamental",
  "trend_signal": "Bullish / Bearish / Neutral",
  "score": 70,
  "key_findings": ["..."],
  "risk_flags": ["..."],
  "raw_data_summary": "..."
}
```

保持该结构可以避免修改融合模块和最终报告模块。

## 评分设计

采用“Python 透明预评分 + LLM 解读”的方式。Python 根据指标给出一个保守的分数提示，LLM 负责把指标转化成自然语言结论和风险标签。

建议权重：

| 维度 | 权重 |
| --- | ---: |
| 盈利能力 | 30 |
| 成长性 | 20 |
| 估值水平 | 20 |
| 财务安全 | 15 |
| 现金流质量 | 15 |

评分应保持保守。如果缺失数据较多，分数应偏中性，并在数据质量说明中突出提示。

## 错误处理

基本面节点应保留现有“单点失败不拖垮整体 Agent”的风格：

- akshare 导入失败或接口失败时，返回部分数据或空字典。
- 指标计算避免除零错误和非数值字段崩溃。
- 缺失指标统一显示为 `N/A`。
- LLM 输出解析失败时，回退为中性的 `FactorEvidence`。

## 测试

测试只聚焦基本面模块。

建议测试：

- 完整样例财报数据下，指标计算结果正确。
- 字段缺失时，指标返回 `N/A` 或使用兜底值。
- 除零场景不会抛异常。
- 格式化输出包含估值、盈利能力、成长性、财务安全、现金流质量、数据质量等主要部分。
- 使用 mock planner 时，`fundamental_analysis_node` 能返回 `factor_name="fundamental"` 的 `FactorEvidence`。

现有全流程测试尽量不改，除非需要适配更丰富的基本面 prompt。

## 验收标准

- 基本面节点使用财报数据，或使用清晰说明的兜底数据。
- 在数据允许时，输出 PE、PB、ROE、利润率、成长性、负债和现金流质量指标。
- 缺失数据会在 prompt 输入和最终分析中体现，而不是被 LLM 猜测。
- 不修改其他因子模块。
- 现有图结构契约和 `FactorEvidence` schema 保持兼容。
- 聚焦测试覆盖新增的计算和格式化行为。
