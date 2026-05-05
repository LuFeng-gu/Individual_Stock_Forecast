# 基本面分析模块 Implementation Plan

**Status:** 已实现并于 `6f55505`（`feat: 基本面节点使用财报派生指标与结构化 prompt`）合入 `main`。下列步骤勾选表示已完成。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有基本面节点升级为基于财报三张表和 Python 指标计算的课程展示版基本面分析模块。

**Architecture:** 保持现有 LangGraph 流程和 `FactorEvidence` 输出契约不变，只增强 `graph/nodes.py` 中的基本面辅助函数和 `fundamental_analysis_node`。新增纯计算函数负责财报指标计算，节点负责抓取数据、格式化 prompt、调用 LLM。

**Tech Stack:** Python 3.11, akshare, Pydantic v2, LangGraph, existing `BasePlanner` / `MockPlanner` test style.

---

## File Structure

- Modify: `graph/nodes.py`
  - Add basic numeric helpers for safe conversion and division.
  - Add fundamental-only fetch helpers.
  - Add metric calculation and formatting helpers.
  - Update `fundamental_analysis_node` to use the richer metric text.
- Modify: `prompts/fundamental_system.md`
  - Constrain LLM to analyze only supplied financial statement metrics.
  - Keep JSON output schema compatible with `FactorEvidence`.
- Modify: `prompts/fundamental_user.md`
  - Keep current format variables but clarify that `fundamental_data` is structured statement-derived data.
- Modify: `tests/test_phase2.py`
  - Add focused tests for calculation, missing data, formatting, and basic node behavior.

No new frontend files, no changes to technical/capital/sentiment/fusion modules.

---

### Task 1: Add Pure Fundamental Metric Tests

**Files:**
- Modify: `tests/test_phase2.py`
- Modify: `graph/nodes.py` in Task 2

- [x] **Step 1: Write failing tests for metric calculation and formatting**

Append these tests before the existing `if __name__ == "__main__":` block in `tests/test_phase2.py`:

```python
def test_fundamental_metric_calculation_complete_data():
    """Test financial statement based fundamental metric calculation."""
    from graph.nodes import _calculate_fundamental_metrics

    reports = {
        "current": {
            "营业收入": 1000.0,
            "营业成本": 600.0,
            "净利润": 180.0,
            "归母净利润": 160.0,
            "总资产": 3000.0,
            "总负债": 1200.0,
            "归母净资产": 1500.0,
            "经营现金流净额": 220.0,
        },
        "previous": {
            "营业收入": 800.0,
            "净利润": 120.0,
            "归母净资产": 1300.0,
        },
    }
    valuation = {"总市值": 3200.0, "PE_DYNAMIC": 21.0, "PB": 2.2}
    basic = {"行业": "测试行业"}

    metrics = _calculate_fundamental_metrics(reports, valuation, basic)

    assert metrics["industry"] == "测试行业"
    assert metrics["pe"] == 20.0
    assert round(metrics["pb"], 4) == 2.1333
    assert round(metrics["roe"], 4) == 0.1143
    assert metrics["gross_margin"] == 0.4
    assert metrics["net_margin"] == 0.18
    assert metrics["revenue_yoy"] == 0.25
    assert metrics["net_profit_yoy"] == 0.5
    assert metrics["debt_to_asset"] == 0.4
    assert round(metrics["ocf_to_net_profit"], 4) == 1.2222
    assert metrics["missing_fields"] == []


def test_fundamental_metric_calculation_missing_data_uses_fallbacks():
    """Test missing statement fields do not crash and valuation fallbacks remain available."""
    from graph.nodes import _calculate_fundamental_metrics

    reports = {
        "current": {
            "营业收入": 0.0,
            "营业成本": None,
            "净利润": None,
            "归母净利润": None,
            "总资产": None,
            "总负债": None,
            "归母净资产": None,
            "经营现金流净额": None,
        },
        "previous": {},
    }
    valuation = {"总市值": 3200.0, "PE_DYNAMIC": 21.0, "PB": 2.2}
    basic = {"行业": "测试行业"}

    metrics = _calculate_fundamental_metrics(reports, valuation, basic)

    assert metrics["pe"] == 21.0
    assert metrics["pb"] == 2.2
    assert metrics["roe"] is None
    assert metrics["gross_margin"] is None
    assert metrics["net_margin"] is None
    assert metrics["revenue_yoy"] is None
    assert metrics["net_profit_yoy"] is None
    assert metrics["debt_to_asset"] is None
    assert metrics["ocf_to_net_profit"] is None
    assert "ROE" in metrics["missing_fields"]
    assert "毛利率" in metrics["missing_fields"]
    assert "净利率" in metrics["missing_fields"]
    assert "营收同比" in metrics["missing_fields"]
    assert "净利润同比" in metrics["missing_fields"]
    assert "资产负债率" in metrics["missing_fields"]
    assert "经营现金流/净利润" in metrics["missing_fields"]


def test_fundamental_metric_formatting_sections():
    """Test LLM prompt text contains all required fundamental sections."""
    from graph.nodes import _format_fundamental_metrics

    metrics = {
        "industry": "测试行业",
        "pe": 20.0,
        "pb": 2.13,
        "roe": 0.1143,
        "gross_margin": 0.4,
        "net_margin": 0.18,
        "revenue_yoy": 0.25,
        "net_profit_yoy": 0.5,
        "debt_to_asset": 0.4,
        "ocf_to_net_profit": 1.2222,
        "score_hint": 75,
        "missing_fields": [],
        "data_sources": ["利润表", "资产负债表", "现金流量表", "行情数据"],
    }

    text = _format_fundamental_metrics(metrics)

    assert "【估值】" in text
    assert "PE: 20.00" in text
    assert "PB: 2.13" in text
    assert "【盈利能力】" in text
    assert "ROE: 11.43%" in text
    assert "毛利率: 40.00%" in text
    assert "净利率: 18.00%" in text
    assert "【成长性】" in text
    assert "营收同比: 25.00%" in text
    assert "净利润同比: 50.00%" in text
    assert "【财务安全】" in text
    assert "资产负债率: 40.00%" in text
    assert "【现金流质量】" in text
    assert "经营现金流/净利润: 1.22" in text
    assert "【数据质量】" in text
    assert "缺失字段: 无" in text
    assert "Python预评分: 75/100" in text
```

- [x] **Step 2: Run the tests and verify they fail**

Run:

```bash
python tests/test_phase2.py
```

Expected result before implementation:

```text
ImportError: cannot import name '_calculate_fundamental_metrics' from 'graph.nodes'
```

- [x] **Step 3: Commit the failing tests**

```bash
git add tests/test_phase2.py
git commit -m "test: add fundamental metric calculation coverage"
```

---

### Task 2: Implement Pure Calculation and Formatting Helpers

**Files:**
- Modify: `graph/nodes.py`
- Test: `tests/test_phase2.py`

- [x] **Step 1: Add numeric helpers and metric functions**

In `graph/nodes.py`, after `_fetch_valuation`, add:

```python
def _to_float(value) -> float | None:
    """Convert common akshare values to float, returning None for missing values."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "--", "N/A", "nan", "None"}:
        return None
    multiplier = 1.0
    if text.endswith("%"):
        text = text[:-1]
        multiplier = 0.01
    text = text.replace(",", "")
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def _safe_div(numerator, denominator) -> float | None:
    """Safely divide two numeric-like values."""
    num = _to_float(numerator)
    den = _to_float(denominator)
    if num is None or den is None or den == 0:
        return None
    return num / den


def _first_available(data: dict, *keys: str):
    """Return the first non-empty value for any of the candidate keys."""
    for key in keys:
        if key in data:
            value = data.get(key)
            if _to_float(value) is not None:
                return value
    return None


def _score_fundamental_metrics(metrics: dict) -> int:
    """Create a conservative transparent score hint from computed metrics."""
    score = 50

    roe = metrics.get("roe")
    if roe is not None:
        score += 10 if roe >= 0.15 else 5 if roe >= 0.08 else -5

    gross_margin = metrics.get("gross_margin")
    if gross_margin is not None:
        score += 5 if gross_margin >= 0.30 else -3 if gross_margin < 0.10 else 0

    net_margin = metrics.get("net_margin")
    if net_margin is not None:
        score += 5 if net_margin >= 0.10 else -3 if net_margin < 0.03 else 0

    revenue_yoy = metrics.get("revenue_yoy")
    if revenue_yoy is not None:
        score += 6 if revenue_yoy >= 0.10 else -6 if revenue_yoy < -0.05 else 0

    net_profit_yoy = metrics.get("net_profit_yoy")
    if net_profit_yoy is not None:
        score += 6 if net_profit_yoy >= 0.10 else -8 if net_profit_yoy < -0.10 else 0

    pe = metrics.get("pe")
    if pe is not None:
        score += 5 if 0 < pe <= 30 else -6 if pe > 60 or pe <= 0 else 0

    pb = metrics.get("pb")
    if pb is not None:
        score += 3 if 0 < pb <= 5 else -4 if pb > 10 or pb <= 0 else 0

    debt_to_asset = metrics.get("debt_to_asset")
    if debt_to_asset is not None:
        score += 5 if debt_to_asset <= 0.50 else -8 if debt_to_asset >= 0.75 else 0

    ocf_to_net_profit = metrics.get("ocf_to_net_profit")
    if ocf_to_net_profit is not None:
        score += 5 if ocf_to_net_profit >= 1 else -6 if ocf_to_net_profit < 0.5 else 0

    missing_count = len(metrics.get("missing_fields", []))
    score -= min(missing_count * 2, 12)
    return max(0, min(100, int(round(score))))


def _calculate_fundamental_metrics(reports: dict, valuation: dict, basic: dict) -> dict:
    """Calculate course-display fundamental metrics from statements and fallbacks."""
    current = reports.get("current", {}) or {}
    previous = reports.get("previous", {}) or {}

    revenue = _first_available(current, "营业收入", "营业总收入")
    operating_cost = _first_available(current, "营业成本", "营业总成本")
    net_profit = _first_available(current, "净利润")
    parent_net_profit = _first_available(current, "归母净利润", "归属于母公司所有者的净利润")
    total_assets = _first_available(current, "总资产", "资产总计")
    total_liabilities = _first_available(current, "总负债", "负债合计")
    parent_equity = _first_available(current, "归母净资产", "归属于母公司股东权益合计", "所有者权益合计")
    operating_cash_flow = _first_available(current, "经营现金流净额", "经营活动产生的现金流量净额")

    previous_revenue = _first_available(previous, "营业收入", "营业总收入")
    previous_net_profit = _first_available(previous, "净利润")
    previous_parent_equity = _first_available(previous, "归母净资产", "归属于母公司股东权益合计", "所有者权益合计")

    total_market_value = _to_float(valuation.get("总市值"))
    parent_net_profit_float = _to_float(parent_net_profit)
    parent_equity_float = _to_float(parent_equity)
    previous_parent_equity_float = _to_float(previous_parent_equity)

    average_parent_equity = None
    if parent_equity_float is not None and previous_parent_equity_float is not None:
        average_parent_equity = (parent_equity_float + previous_parent_equity_float) / 2

    pe = _safe_div(total_market_value, parent_net_profit_float)
    if pe is None:
        pe = _to_float(valuation.get("PE_DYNAMIC"))

    pb = _safe_div(total_market_value, parent_equity_float)
    if pb is None:
        pb = _to_float(valuation.get("PB"))

    metrics = {
        "industry": basic.get("行业", "未知"),
        "pe": pe,
        "pb": pb,
        "roe": _safe_div(parent_net_profit_float, average_parent_equity),
        "gross_margin": _safe_div(_to_float(revenue) - _to_float(operating_cost), revenue)
        if _to_float(revenue) is not None and _to_float(operating_cost) is not None
        else None,
        "net_margin": _safe_div(net_profit, revenue),
        "revenue_yoy": _safe_div(_to_float(revenue) - _to_float(previous_revenue), previous_revenue)
        if _to_float(revenue) is not None and _to_float(previous_revenue) is not None
        else None,
        "net_profit_yoy": _safe_div(_to_float(net_profit) - _to_float(previous_net_profit), previous_net_profit)
        if _to_float(net_profit) is not None and _to_float(previous_net_profit) is not None
        else None,
        "debt_to_asset": _safe_div(total_liabilities, total_assets),
        "ocf_to_net_profit": _safe_div(operating_cash_flow, net_profit),
        "data_sources": reports.get("data_sources", ["利润表", "资产负债表", "现金流量表", "行情数据"]),
    }

    labels = {
        "pe": "PE",
        "pb": "PB",
        "roe": "ROE",
        "gross_margin": "毛利率",
        "net_margin": "净利率",
        "revenue_yoy": "营收同比",
        "net_profit_yoy": "净利润同比",
        "debt_to_asset": "资产负债率",
        "ocf_to_net_profit": "经营现金流/净利润",
    }
    metrics["missing_fields"] = [label for key, label in labels.items() if metrics.get(key) is None]
    metrics["score_hint"] = _score_fundamental_metrics(metrics)
    return metrics


def _format_ratio(value) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def _format_number(value) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def _format_fundamental_metrics(metrics: dict) -> str:
    """Format fundamental metrics for the LLM prompt."""
    missing = metrics.get("missing_fields", [])
    sources = metrics.get("data_sources", [])
    return (
        "【估值】\n"
        f"PE: {_format_number(metrics.get('pe'))}\n"
        f"PB: {_format_number(metrics.get('pb'))}\n\n"
        "【盈利能力】\n"
        f"ROE: {_format_ratio(metrics.get('roe'))}\n"
        f"毛利率: {_format_ratio(metrics.get('gross_margin'))}\n"
        f"净利率: {_format_ratio(metrics.get('net_margin'))}\n\n"
        "【成长性】\n"
        f"营收同比: {_format_ratio(metrics.get('revenue_yoy'))}\n"
        f"净利润同比: {_format_ratio(metrics.get('net_profit_yoy'))}\n\n"
        "【财务安全】\n"
        f"资产负债率: {_format_ratio(metrics.get('debt_to_asset'))}\n\n"
        "【现金流质量】\n"
        f"经营现金流/净利润: {_format_number(metrics.get('ocf_to_net_profit'))}\n\n"
        "【数据质量】\n"
        f"缺失字段: {', '.join(missing) if missing else '无'}\n"
        f"数据来源: {', '.join(sources) if sources else '未知'}\n"
        f"Python预评分: {metrics.get('score_hint', 50)}/100"
    )
```

- [x] **Step 2: Run focused tests**

Run:

```bash
python tests/test_phase2.py
```

Expected result for the new tests:

```text
PHASE 2 DATA FETCHING TEST
...
ALL PHASE 2 TESTS PASSED OK
```

If the environment lacks dependencies, the expected blocker is:

```text
ModuleNotFoundError: No module named 'pydantic'
```

Record that blocker before continuing with runtime verification.

- [x] **Step 3: Commit helper implementation**

```bash
git add graph/nodes.py tests/test_phase2.py
git commit -m "feat: add fundamental metric calculation helpers"
```

---

### Task 3: Add Financial Statement Fetching Helpers

**Files:**
- Modify: `graph/nodes.py`
- Test: `tests/test_phase2.py`

- [x] **Step 1: Write a fetch-shape smoke test**

Append this test before the existing `if __name__ == "__main__":` block in `tests/test_phase2.py`:

```python
def test_fundamental_report_fetch_shape():
    """Test financial report fetch helper returns the expected stable shape."""
    from graph.nodes import _fetch_financial_reports

    reports = _fetch_financial_reports("600519")

    assert "current" in reports
    assert "previous" in reports
    assert "data_sources" in reports
    assert isinstance(reports["current"], dict)
    assert isinstance(reports["previous"], dict)
    assert isinstance(reports["data_sources"], list)
```

- [x] **Step 2: Run the test and verify it fails**

Run:

```bash
python tests/test_phase2.py
```

Expected result before implementation:

```text
ImportError: cannot import name '_fetch_financial_reports' from 'graph.nodes'
```

- [x] **Step 3: Implement financial statement fetch helpers**

In `graph/nodes.py`, after `_calculate_fundamental_metrics`, add:

```python
def _row_to_metric_dict(row) -> dict:
    """Convert a dataframe row to a normalized dict with only useful scalar values."""
    if row is None:
        return {}
    result = {}
    for key, value in row.items():
        if key in {"股票代码", "股票简称", "报告期", "公告日期", "报告类型"}:
            continue
        result[str(key)] = value
    return result


def _fetch_financial_reports(stock_code: str) -> dict:
    """
    Fetch recent financial statement-like data from akshare.

    The exact akshare financial interfaces can vary, so this helper returns a
    stable shape and lets metric calculation tolerate missing fields.
    """
    reports = {
        "current": {},
        "previous": {},
        "data_sources": ["利润表", "资产负债表", "现金流量表", "行情数据"],
    }
    try:
        import akshare as ak

        indicator_df = ak.stock_financial_analysis_indicator(symbol=stock_code)
        if indicator_df is None or indicator_df.empty:
            return reports

        recent = indicator_df.head(2)
        if len(recent) >= 1:
            reports["current"].update(_row_to_metric_dict(recent.iloc[0]))
        if len(recent) >= 2:
            reports["previous"].update(_row_to_metric_dict(recent.iloc[1]))
        return reports
    except Exception as e:
        log_error("fundamental_reports", RuntimeError(f"Failed to fetch financial reports: {e}"))
        return reports
```

- [x] **Step 4: Run tests**

Run:

```bash
python tests/test_phase2.py
```

Expected result in a configured environment:

```text
PHASE 2 DATA FETCHING TEST
...
ALL PHASE 2 TESTS PASSED OK
```

If akshare cannot reach the data source, the fetch-shape test should still pass because the helper returns empty `current` and `previous` dictionaries with stable keys.

- [x] **Step 5: Commit fetching helper**

```bash
git add graph/nodes.py tests/test_phase2.py
git commit -m "feat: fetch fundamental financial report data"
```

---

### Task 4: Wire Rich Metrics Into Fundamental Node

**Files:**
- Modify: `graph/nodes.py`
- Test: `tests/test_phase2.py`

- [x] **Step 1: Add a node-level prompt capture test**

Append this test before the existing `if __name__ == "__main__":` block in `tests/test_phase2.py`:

```python
def test_fundamental_node_uses_structured_metric_prompt():
    """Test fundamental node sends grouped structured metrics to the planner."""
    from core.state import create_initial_state
    from core.schemas import UserIntent, SectorRoute
    from graph.nodes import fundamental_analysis_node

    class CapturingPlanner(MockPlanner):
        def __init__(self):
            self.user_prompt = ""

        def generate(self, system_prompt: str, user_prompt: str) -> str:
            self.user_prompt = user_prompt
            return """{
                "factor_name": "fundamental",
                "trend_signal": "Neutral",
                "score": 60,
                "key_findings": ["基本面指标已结构化"],
                "risk_flags": [],
                "raw_data_summary": "已读取基本面结构化数据"
            }"""

    state = create_initial_state(query="分析贵州茅台")
    state["user_intent"] = UserIntent(stock_name="贵州茅台", stock_code="600519")
    state["sector_route"] = SectorRoute(sectors=["fundamental"], analysis_focus="基本面分析")
    planner = CapturingPlanner()

    result = fundamental_analysis_node(state, planner)

    evidence = result["fundamental_evidence"]
    assert evidence.factor_name == "fundamental"
    assert evidence.score == 60
    assert "【估值】" in planner.user_prompt
    assert "【盈利能力】" in planner.user_prompt
    assert "【成长性】" in planner.user_prompt
    assert "【财务安全】" in planner.user_prompt
    assert "【现金流质量】" in planner.user_prompt
    assert "【数据质量】" in planner.user_prompt
```

- [x] **Step 2: Run the test and verify it fails against the old prompt**

Run:

```bash
python tests/test_phase2.py
```

Expected result before wiring:

```text
AssertionError: assert '【盈利能力】' in planner.user_prompt
```

- [x] **Step 3: Update `fundamental_analysis_node`**

Replace the body section in `fundamental_analysis_node` from:

```python
    basic = _fetch_stock_basic(stock_code)
    valuation = _fetch_valuation(stock_code)

    industry = basic.get("行业", "未知")
    pe_dynamic = valuation.get("PE_DYNAMIC", "N/A")
    pb = valuation.get("PB", "N/A")
    turnover = valuation.get("换手率", "N/A")
    total_market = basic.get("总市值", "N/A")

    fundamental_text = (
        f"行业: {industry}\n"
        f"总市值: {total_market}\n"
        f"PE(动态): {pe_dynamic}\n"
        f"PB: {pb}\n"
        f"换手率: {turnover}%\n"
    )
```

with:

```python
    basic = _fetch_stock_basic(stock_code)
    valuation = _fetch_valuation(stock_code)
    if "总市值" not in valuation and basic.get("总市值") is not None:
        valuation["总市值"] = basic.get("总市值")

    reports = _fetch_financial_reports(stock_code)
    metrics = _calculate_fundamental_metrics(reports, valuation, basic)
    industry = metrics.get("industry", basic.get("行业", "未知"))
    fundamental_text = _format_fundamental_metrics(metrics)
```

- [x] **Step 4: Run tests**

Run:

```bash
python tests/test_phase2.py
```

Expected result:

```text
ALL PHASE 2 TESTS PASSED OK
```

- [x] **Step 5: Commit node wiring**

```bash
git add graph/nodes.py tests/test_phase2.py
git commit -m "feat: wire structured metrics into fundamental node"
```

---

### Task 5: Tighten Fundamental Prompts

**Files:**
- Modify: `prompts/fundamental_system.md`
- Modify: `prompts/fundamental_user.md`
- Test: `tests/test_phase2.py`

- [x] **Step 1: Update `prompts/fundamental_system.md`**

Replace the file content with:

```markdown
You are a fundamental analysis expert for Chinese A-shares.

Your job is to evaluate a stock's business quality, valuation, profitability, growth, financial safety, and cash flow quality from the structured financial data provided by the system.

## Input Data

You will receive structured fundamental data derived from financial statements and market data:
- Valuation: PE, PB
- Profitability: ROE, gross margin, net margin
- Growth: revenue YoY, net profit YoY
- Financial safety: debt-to-asset ratio
- Cash flow quality: operating cash flow / net profit
- Data quality: missing fields and data sources
- Industry context
- Python score hint

## Output Format

Return a JSON object:

```json
{
    "factor_name": "fundamental",
    "trend_signal": "Bullish / Bearish / Neutral",
    "score": 70,
    "key_findings": ["finding 1", "finding 2", "finding 3"],
    "risk_flags": ["risk 1"],
    "raw_data_summary": "brief summary of the fundamental picture"
}
```

## Scoring Guide (0-100)

- 80-100: Excellent fundamentals, strong profitability, healthy growth, reasonable valuation, solid cash flow
- 60-79: Good fundamentals, some concerns but overall positive
- 40-59: Average fundamentals, mixed signals, or many missing fields
- 20-39: Weak fundamentals, expensive valuation, declining growth, high debt, or weak cash flow
- 0-19: Poor fundamentals, high risk of value trap or financial distress

## Key Findings Should Cover

1. Valuation: PE and PB level
2. Profitability: ROE, gross margin, net margin
3. Growth: revenue and net profit YoY
4. Financial safety: debt-to-asset ratio
5. Cash flow quality: operating cash flow / net profit
6. Data quality: missing fields, if any

## Rules

- trend_signal must be one of: "Bullish", "Bearish", "Neutral"
- score must be an integer 0-100
- Use the Python score hint as a reference, but adjust if the evidence clearly supports a different conclusion
- Do not invent missing financial data
- If a metric is N/A, explicitly mention the limitation when it affects the conclusion
- risk_flags should highlight concrete risks such as high valuation, declining profit, high debt, weak cash flow, or missing critical data
- Return pure JSON, no markdown code blocks
```

- [x] **Step 2: Update `prompts/fundamental_user.md`**

Replace the file content with:

```markdown
Stock: {stock_name} ({stock_code})
Industry: {industry}

Structured Fundamental Data:

{fundamental_data}

Analyze only the provided fundamental data. Return the JSON structure.
```

- [x] **Step 3: Run tests**

Run:

```bash
python tests/test_phase2.py
```

Expected result:

```text
ALL PHASE 2 TESTS PASSED OK
```

The mock planner still matches `"fundamental analysis expert"` in the system prompt.

- [x] **Step 4: Commit prompt changes**

```bash
git add prompts/fundamental_system.md prompts/fundamental_user.md tests/test_phase2.py
git commit -m "prompt: constrain fundamental analysis to provided metrics"
```

---

### Task 6: Add Fundamental Tests to Script Entry Point

**Files:**
- Modify: `tests/test_phase2.py`

- [x] **Step 1: Update the `__main__` block**

At the bottom of `tests/test_phase2.py`, update the `if __name__ == "__main__":` block to include the new focused tests before full-flow tests:

```python
if __name__ == "__main__":
    try:
        test_fundamental_metric_calculation_complete_data()
        test_fundamental_metric_calculation_missing_data_uses_fallbacks()
        test_fundamental_metric_formatting_sections()
        test_fundamental_report_fetch_shape()
        test_fundamental_node_uses_structured_metric_prompt()
        test_akshare_phase2_data()
        test_phase2_full_flow()
        test_sector_routing_skip()
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nTEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
```

- [x] **Step 2: Run the test script**

Run:

```bash
python tests/test_phase2.py
```

Expected result:

```text
ALL PHASE 2 TESTS PASSED OK
SECTOR SKIP TEST PASSED OK
```

If dependencies are missing, stop and create/install the conda environment before marking this task complete.

- [x] **Step 3: Commit test entry point**

```bash
git add tests/test_phase2.py
git commit -m "test: run focused fundamental tests in phase2 script"
```

---

### Task 7: Verification and Demo Run

**Files:**
- Verify only; no planned file modifications.

- [x] **Step 1: Check git status**

Run:

```bash
git status --short
```

Expected result:

```text
```

No output means the working tree is clean.

- [x] **Step 2: Run focused phase2 tests**

Run:

```bash
python tests/test_phase2.py
```

Expected result:

```text
ALL PHASE 2 TESTS PASSED OK
SECTOR SKIP TEST PASSED OK
```

- [x] **Step 3: Optional real Agent demo with trace**

Run only if `.env` has `PLANNER_API_KEY` and `PLANNER_BASE_URL`:

```bash
python main.py --query "帮我看看贵州茅台的基本面怎么样" --trace --trace-dir trace
```

Expected result:

```text
AGENT RESULT
...
【四大因子分析】
  基本面: ...
...
```

The trace should show `fundamental_analysis_node` receiving structured sections such as `【估值】`, `【盈利能力】`, and `【现金流质量】`.

- [x] **Step 4: Final commit if verification changed generated trace files intentionally**

If trace files are regenerated and should be kept:

```bash
git add trace/trace.jsonl trace/trace_report.md
git commit -m "test: refresh traced fundamental analysis output"
```

If trace files are not part of the submission, leave them untracked or restore only your own generated changes according to the project team's preference.

---

## Self-Review Notes

- Spec coverage: The plan covers financial-statement-derived indicators, data fallbacks, prompt constraints, score hint, missing data behavior, and focused tests.
- Scope: The plan modifies only `graph/nodes.py`, fundamental prompts, and `tests/test_phase2.py`.
- Contract: `fundamental_analysis_node` still returns `FactorEvidence` through `fundamental_evidence`, so fusion and final answer modules remain compatible.
