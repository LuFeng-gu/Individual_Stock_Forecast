"""
LangGraph node functions for the stock forecast agent workflow.

Phase 1: intent_clarification → market_structure → final_answer
Phase 2: + sector_router → 4 factor nodes → cross_sector_fusion → final_answer
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from core.state import AgentState
from core.constants import AgentStatus
from core.schemas import (
    EvidenceItem,
    UserIntent,
    MarketStructure,
    SectorRoute,
    FactorEvidence,
    CompositeAssessment,
    FinalAnswer,
)
from core.logging import log_node_start, log_node_end, log_info, log_error
from planner.base import BasePlanner


# =============================================================================
# Stock Data Helpers (internal, akshare-based)
# =============================================================================

_STOCK_NAME_CACHE: dict[str, str] | None = None


def _load_stock_name_cache() -> dict[str, str]:
    """Load or build a name -> code mapping cache."""
    global _STOCK_NAME_CACHE
    if _STOCK_NAME_CACHE is not None:
        return _STOCK_NAME_CACHE
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        mapping = {}
        for _, row in df.iterrows():
            code = str(row["code"]).strip()
            name = str(row["name"]).strip()
            mapping[name] = code
            clean_name = name.replace("*ST", "").replace("ST", "").strip()
            if clean_name and clean_name != name:
                mapping[clean_name] = code
        _STOCK_NAME_CACHE = mapping
        return mapping
    except Exception as e:
        log_error("stock_cache", RuntimeError(f"Failed to load stock cache: {e}"))
        return {}


def _resolve_stock_code(stock_name: str) -> str:
    """Resolve stock name to 6-digit code."""
    if stock_name.isdigit() and len(stock_name) == 6:
        return stock_name
    cache = _load_stock_name_cache()
    if stock_name in cache:
        return cache[stock_name]
    for name, code in cache.items():
        if stock_name in name or name in stock_name:
            return code
    return ""


def _fetch_stock_basic(stock_code: str) -> dict:
    """Fetch basic stock info via akshare."""
    try:
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=stock_code)
        return dict(zip(df["item"], df["value"]))
    except Exception as e:
        return {"股票代码": stock_code, "股票简称": stock_code}


def _fetch_recent_kline(stock_code: str, days: int = 10) -> list[dict]:
    """Fetch recent daily K-line data."""
    try:
        import akshare as ak
        end = datetime.now()
        start = end - timedelta(days=days + 15)
        df = ak.stock_zh_a_hist(
            symbol=stock_code, period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"), adjust="qfq",
        )
        if df.empty:
            return []
        recent = df.tail(days)
        return recent[["日期", "收盘", "涨跌幅", "成交量"]].to_dict("records")
    except Exception as e:
        return []


def _fetch_valuation(stock_code: str) -> dict:
    """Fetch latest valuation metrics (PE, PB, etc.) from real-time market data."""
    try:
        import akshare as ak
        # stock_zh_a_spot_em returns all A-shares real-time data including PE/PB
        df = ak.stock_zh_a_spot_em()
        if "代码" not in df.columns:
            return {}
        row = df[df["代码"] == stock_code]
        if row.empty:
            return {}
        latest = row.iloc[0]
        return {
            "PE_DYNAMIC": latest.get("市盈率-动态", "N/A"),
            "PB": latest.get("市净率", "N/A"),
            "换手率": latest.get("换手率", "N/A"),
            "振幅": latest.get("振幅", "N/A"),
        }
    except Exception as e:
        return {}


def _fetch_capital_flow(stock_code: str, days: int = 5) -> list[dict]:
    """Fetch recent capital flow data."""
    try:
        import akshare as ak
        df = ak.stock_individual_fund_flow(stock=stock_code, market="sh")
        if df.empty:
            return []
        recent = df.head(days)
        return recent[["日期", "主力净流入-净额", "主力净流入-净占比", "小单净流入-净额"]].to_dict("records")
    except Exception as e:
        return []


def _fetch_news(stock_code: str, top_n: int = 5) -> list[dict]:
    """Fetch recent news headlines."""
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol=stock_code)
        if df.empty:
            return []
        recent = df.head(top_n)
        return recent[["新闻标题", "发布时间"]].to_dict("records")
    except Exception as e:
        return []


def _fetch_hot_concepts(top_n: int = 10) -> list[dict]:
    """Fetch today's hot concept sectors."""
    try:
        import akshare as ak
        df = ak.stock_board_concept_name_em()
        hot = df.nlargest(top_n, "涨跌幅")
        return hot[["板块名称", "涨跌幅"]].to_dict("records")
    except Exception as e:
        return []


def _calculate_ma(kline: list[dict]) -> dict:
    """Calculate moving averages from kline data."""
    if len(kline) < 5:
        return {}
    closes = [d["收盘"] for d in kline]
    return {
        "MA5": sum(closes[-5:]) / 5 if len(closes) >= 5 else None,
        "MA20": sum(closes[-20:]) / 20 if len(closes) >= 20 else None,
        "MA60": sum(closes[-60:]) / 60 if len(closes) >= 60 else None,
    }


def _load_prompt(prompt_name: str) -> str:
    """Load a prompt markdown file from the prompts/ directory."""
    module_dir = Path(__file__).parent.parent
    prompt_path = module_dir / "prompts" / f"{prompt_name}.md"
    if not prompt_path.exists():
        return ""
    return prompt_path.read_text(encoding="utf-8")


def _parse_json_from_llm(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start : end + 1])
        raise


# =============================================================================
# Phase 1 Nodes: Intent & Market Structure
# =============================================================================

def intent_clarification_node(state: AgentState, planner: BasePlanner) -> dict:
    """Parse the user's natural language query into structured intent."""
    log_node_start("intent_clarification_node", {"query": state["query"][:50]})

    query = state["query"]
    system_prompt = _load_prompt("intent_system")
    user_prompt = _load_prompt("intent_user").format(query=query)

    try:
        response_text = planner.generate(system_prompt, user_prompt)
        data = _parse_json_from_llm(response_text)
        intent = UserIntent(**data)
    except Exception as e:
        log_error("intent_clarification", RuntimeError(f"Failed to parse intent: {e}"))
        intent = UserIntent(
            stock_name=query.replace("帮我看看", "").replace("怎么样", "").strip(),
            clarified_query=query,
        )

    if not intent.stock_code and intent.stock_name:
        intent.stock_code = _resolve_stock_code(intent.stock_name)

    log_node_end("intent_clarification_node", {
        "stock": intent.stock_name, "code": intent.stock_code,
        "intent": intent.intent_type, "horizon": intent.time_horizon,
    })
    log_info("intent", {"stock": intent.stock_name, "code": intent.stock_code})
    return {"user_intent": intent}


def market_structure_node(state: AgentState, planner: BasePlanner) -> dict:
    """Analyze the stock's position in the current market landscape."""
    log_node_start("market_structure_node")

    intent = state.get("user_intent")
    if not intent:
        log_error("market_structure", RuntimeError("No user_intent in state"))
        return {"status": AgentStatus.FAILED, "error_message": "Missing user_intent"}

    stock_code = intent.stock_code
    stock_name = intent.stock_name
    if not stock_code:
        return {"status": AgentStatus.FAILED, "error_message": f"无法解析股票代码: {stock_name}"}

    basic_info = _fetch_stock_basic(stock_code)
    kline_data = _fetch_recent_kline(stock_code, days=10)
    hot_concepts = _fetch_hot_concepts(top_n=10)

    kline_summary = ""
    if kline_data:
        latest = kline_data[-1]
        kline_summary = (
            f"最新收盘价: {latest['收盘']}, 最新涨跌幅: {latest['涨跌幅']}%\n"
            f"近{len(kline_data)}日走势: "
            + " → ".join([f"{d['收盘']}({d['涨跌幅']}%)" for d in kline_data[-5:]])
        )

    hot_concepts_text = "\n".join([f"- {c['板块名称']}: {c['涨跌幅']}%" for c in hot_concepts])

    system_prompt = _load_prompt("market_structure_system")
    user_prompt = _load_prompt("market_structure_user").format(
        stock_name=basic_info.get("股票简称", stock_name),
        stock_code=stock_code,
        industry=basic_info.get("行业", "未知"),
        concepts=basic_info.get("概念", "暂无"),
        hot_sectors=hot_concepts_text,
        sector_heat_rank="前10热点" if hot_concepts else "未知",
        change_5d=latest.get("涨跌幅", 0) if kline_data else 0,
        sector_change_5d=0,
        kline_summary=kline_summary,
    )

    try:
        response_text = planner.generate(system_prompt, user_prompt)
        data = _parse_json_from_llm(response_text)
        market_structure = MarketStructure(**data)
    except Exception as e:
        log_error("market_structure", RuntimeError(f"Planner analysis failed: {e}"))
        market_structure = MarketStructure(
            current_market_themes=[c["板块名称"] for c in hot_concepts[:3]],
            stock_themes=[basic_info.get("行业", "")],
            theme_position="未知",
            analysis_summary=f"{stock_name}({stock_code})，行业{basic_info.get('行业', '未知')}，数据获取完成但分析失败。",
        )

    evidence = EvidenceItem(
        source="market_structure",
        content=market_structure.analysis_summary,
        evidence_type="structured",
        confidence=0.75,
        metadata={"stock_code": stock_code, "industry": basic_info.get("行业", "")},
    )

    log_node_end("market_structure_node", {"position": market_structure.theme_position})
    return {"market_structure": market_structure, "evidence_log": [evidence]}


# =============================================================================
# Phase 2 Nodes: Sector Router & Factor Analysis
# =============================================================================

def sector_router_node(state: AgentState, planner: BasePlanner) -> dict:
    """
    Dynamically decide which factor sectors to analyze.

    Based on user intent and market structure.
    """
    log_node_start("sector_router_node")

    intent = state.get("user_intent")
    market = state.get("market_structure")

    if not intent:
        log_error("sector_router", RuntimeError("No user_intent in state"))
        return {"status": AgentStatus.FAILED, "error_message": "Missing user_intent"}

    system_prompt = _load_prompt("sector_route_system")
    user_prompt = _load_prompt("sector_route_user").format(
        stock_name=intent.stock_name,
        stock_code=intent.stock_code,
        intent_type=intent.intent_type,
        time_horizon=intent.time_horizon,
        risk_preference=intent.risk_preference,
        clarified_query=intent.clarified_query,
        theme_position=market.theme_position if market else "未知",
        stock_themes=", ".join(market.stock_themes) if market else "未知",
        market_themes=", ".join(market.current_market_themes) if market else "未知",
        market_sentiment=market.market_sentiment if market else "未知",
    )

    try:
        response_text = planner.generate(system_prompt, user_prompt)
        data = _parse_json_from_llm(response_text)
        route = SectorRoute(**data)
    except Exception as e:
        log_error("sector_router", RuntimeError(f"Routing failed: {e}"))
        # Default: analyze all sectors
        route = SectorRoute(
            sectors=["technical", "fundamental", "capital", "sentiment"],
            analysis_focus="全面分析",
        )

    log_node_end("sector_router_node", {"sectors": route.sectors})
    log_info("sector_router", {"sectors": route.sectors, "focus": route.analysis_focus})
    return {"sector_route": route}


def _should_analyze(state: AgentState, sector: str) -> bool:
    """Check if a sector should be analyzed based on the route."""
    route = state.get("sector_route")
    if not route:
        return True  # Default: analyze all if no route
    return sector in route.sectors


def _factor_evidence_to_dict(evidence: FactorEvidence | None) -> str:
    """Format FactorEvidence for prompt injection."""
    if not evidence:
        return "未分析"
    return (
        f"趋势信号: {evidence.trend_signal}, 评分: {evidence.score}/100\n"
        f"关键发现: {', '.join(evidence.key_findings)}\n"
        f"风险标记: {', '.join(evidence.risk_flags) if evidence.risk_flags else '无'}"
    )


def technical_analysis_node(state: AgentState, planner: BasePlanner) -> dict:
    """Technical factor analysis: K-line, MA, MACD, RSI, volume."""
    log_node_start("technical_analysis_node")

    if not _should_analyze(state, "technical"):
        log_info("technical_analysis", {"status": "skipped"})
        return {"technical_evidence": None}

    intent = state.get("user_intent")
    stock_code = intent.stock_code if intent else ""
    stock_name = intent.stock_name if intent else ""

    kline = _fetch_recent_kline(stock_code, days=20)
    ma = _calculate_ma(kline)

    kline_text = "\n".join([f"  {d['日期']}: 收{d['收盘']} 涨跌{d['涨跌幅']}% 量{d['成交量']}" for d in kline[-10:]])
    ma_text = f"MA5: {ma.get('MA5', 'N/A')}, MA20: {ma.get('MA20', 'N/A')}, MA60: {ma.get('MA60', 'N/A')}"

    system_prompt = _load_prompt("technical_system")
    user_prompt = _load_prompt("technical_user").format(
        stock_name=stock_name,
        stock_code=stock_code,
        kline_summary=kline_text,
        indicator_summary=ma_text,
    )

    try:
        response_text = planner.generate(system_prompt, user_prompt)
        data = _parse_json_from_llm(response_text)
        evidence = FactorEvidence(**data)
    except Exception as e:
        log_error("technical_analysis", RuntimeError(f"Analysis failed: {e}"))
        evidence = FactorEvidence(
            factor_name="technical",
            trend_signal="Neutral",
            score=50,
            key_findings=["数据获取或分析失败"],
        )

    item = EvidenceItem(
        source="technical", content=evidence.raw_data_summary or "技术面分析",
        evidence_type="score", score=evidence.score, confidence=0.7,
    )

    log_node_end("technical_analysis_node", {"score": evidence.score, "signal": evidence.trend_signal})
    return {"technical_evidence": evidence, "evidence_log": [item]}


def fundamental_analysis_node(state: AgentState, planner: BasePlanner) -> dict:
    """Fundamental factor analysis: PE, PB, ROE, financial health."""
    log_node_start("fundamental_analysis_node")

    if not _should_analyze(state, "fundamental"):
        log_info("fundamental_analysis", {"status": "skipped"})
        return {"fundamental_evidence": None}

    intent = state.get("user_intent")
    stock_code = intent.stock_code if intent else ""
    stock_name = intent.stock_name if intent else ""

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

    system_prompt = _load_prompt("fundamental_system")
    user_prompt = _load_prompt("fundamental_user").format(
        stock_name=stock_name,
        stock_code=stock_code,
        industry=industry,
        fundamental_data=fundamental_text,
    )

    try:
        response_text = planner.generate(system_prompt, user_prompt)
        data = _parse_json_from_llm(response_text)
        evidence = FactorEvidence(**data)
    except Exception as e:
        log_error("fundamental_analysis", RuntimeError(f"Analysis failed: {e}"))
        evidence = FactorEvidence(
            factor_name="fundamental",
            trend_signal="Neutral",
            score=50,
            key_findings=["基本面数据获取或分析失败"],
        )

    item = EvidenceItem(
        source="fundamental", content=evidence.raw_data_summary or "基本面分析",
        evidence_type="score", score=evidence.score, confidence=0.7,
    )

    log_node_end("fundamental_analysis_node", {"score": evidence.score})
    return {"fundamental_evidence": evidence, "evidence_log": [item]}


def capital_analysis_node(state: AgentState, planner: BasePlanner) -> dict:
    """Capital flow factor analysis: main fund, institutional, margin."""
    log_node_start("capital_analysis_node")

    if not _should_analyze(state, "capital"):
        log_info("capital_analysis", {"status": "skipped"})
        return {"capital_evidence": None}

    intent = state.get("user_intent")
    stock_code = intent.stock_code if intent else ""
    stock_name = intent.stock_name if intent else ""

    flow = _fetch_capital_flow(stock_code, days=5)
    flow_text = "\n".join([
        f"  {d['日期']}: 主力净额{d['主力净流入-净额']} 占比{d['主力净流入-净占比']}%"
        for d in flow
    ]) if flow else "暂无资金流向数据"

    system_prompt = _load_prompt("capital_system")
    user_prompt = _load_prompt("capital_user").format(
        stock_name=stock_name,
        stock_code=stock_code,
        capital_data=flow_text,
    )

    try:
        response_text = planner.generate(system_prompt, user_prompt)
        data = _parse_json_from_llm(response_text)
        evidence = FactorEvidence(**data)
    except Exception as e:
        log_error("capital_analysis", RuntimeError(f"Analysis failed: {e}"))
        evidence = FactorEvidence(
            factor_name="capital",
            trend_signal="Neutral",
            score=50,
            key_findings=["资金面数据获取或分析失败"],
        )

    item = EvidenceItem(
        source="capital", content=evidence.raw_data_summary or "资金面分析",
        evidence_type="score", score=evidence.score, confidence=0.65,
    )

    log_node_end("capital_analysis_node", {"score": evidence.score})
    return {"capital_evidence": evidence, "evidence_log": [item]}


def sentiment_analysis_node(state: AgentState, planner: BasePlanner) -> dict:
    """Sentiment factor analysis: news, sector heat, events."""
    log_node_start("sentiment_analysis_node")

    if not _should_analyze(state, "sentiment"):
        log_info("sentiment_analysis", {"status": "skipped"})
        return {"sentiment_evidence": None}

    intent = state.get("user_intent")
    stock_code = intent.stock_code if intent else ""
    stock_name = intent.stock_name if intent else ""

    news = _fetch_news(stock_code, top_n=5)
    news_text = "\n".join([f"  [{d['发布时间']}] {d['新闻标题']}" for d in news]) if news else "暂无新闻"

    hot_concepts = _fetch_hot_concepts(top_n=5)
    concept_text = "\n".join([f"  {c['板块名称']}: {c['涨跌幅']}%" for c in hot_concepts])

    sentiment_text = f"近期新闻:\n{news_text}\n\n热点板块:\n{concept_text}"

    system_prompt = _load_prompt("sentiment_system")
    user_prompt = _load_prompt("sentiment_user").format(
        stock_name=stock_name,
        stock_code=stock_code,
        stock_themes=", ".join(state.get("market_structure", MarketStructure()).stock_themes),
        sentiment_data=sentiment_text,
    )

    try:
        response_text = planner.generate(system_prompt, user_prompt)
        data = _parse_json_from_llm(response_text)
        evidence = FactorEvidence(**data)
    except Exception as e:
        log_error("sentiment_analysis", RuntimeError(f"Analysis failed: {e}"))
        evidence = FactorEvidence(
            factor_name="sentiment",
            trend_signal="Neutral",
            score=50,
            key_findings=["情绪面数据获取或分析失败"],
        )

    item = EvidenceItem(
        source="sentiment", content=evidence.raw_data_summary or "情绪面分析",
        evidence_type="score", score=evidence.score, confidence=0.6,
    )

    log_node_end("sentiment_analysis_node", {"score": evidence.score})
    return {"sentiment_evidence": evidence, "evidence_log": [item]}


# =============================================================================
# Phase 2 Nodes: Cross-Sector Fusion & Final Answer
# =============================================================================

def cross_sector_fusion_node(state: AgentState, planner: BasePlanner) -> dict:
    """
    Synthesize evidence from all factor analyses into a unified assessment.
    """
    log_node_start("cross_sector_fusion_node")

    intent = state.get("user_intent")
    tech = state.get("technical_evidence")
    fund = state.get("fundamental_evidence")
    cap = state.get("capital_evidence")
    sent = state.get("sentiment_evidence")

    system_prompt = _load_prompt("fusion_system")
    user_prompt = _load_prompt("fusion_user").format(
        stock_name=intent.stock_name if intent else "",
        stock_code=intent.stock_code if intent else "",
        time_horizon=intent.time_horizon if intent else "medium",
        technical_evidence=_factor_evidence_to_dict(tech),
        fundamental_evidence=_factor_evidence_to_dict(fund),
        capital_evidence=_factor_evidence_to_dict(cap),
        sentiment_evidence=_factor_evidence_to_dict(sent),
    )

    try:
        response_text = planner.generate(system_prompt, user_prompt)
        data = _parse_json_from_llm(response_text)
        assessment = CompositeAssessment(**data)
    except Exception as e:
        log_error("cross_sector_fusion", RuntimeError(f"Fusion failed: {e}"))
        # Calculate simple average score
        scores = [e.score for e in [tech, fund, cap, sent] if e]
        avg_score = int(sum(scores) / len(scores)) if scores else 50
        assessment = CompositeAssessment(
            composite_score=avg_score,
            trend_direction="震荡",
            position_status="震荡",
            risk_level="中",
            summary="综合分析失败，使用默认评估。",
        )

    evidence = EvidenceItem(
        source="cross_sector_fusion",
        content=assessment.summary,
        evidence_type="structured",
        score=assessment.composite_score,
        confidence=0.75,
    )

    log_node_end("cross_sector_fusion_node", {
        "score": assessment.composite_score,
        "trend": assessment.trend_direction,
        "risk": assessment.risk_level,
    })
    return {"composite_assessment": assessment, "evidence_log": [evidence]}


def final_answer_node(state: AgentState, planner: BasePlanner) -> dict:
    """Generate the final structured report."""
    log_node_start("final_answer_node")

    intent = state.get("user_intent")
    market = state.get("market_structure")
    route = state.get("sector_route")
    tech = state.get("technical_evidence")
    fund = state.get("fundamental_evidence")
    cap = state.get("capital_evidence")
    sent = state.get("sentiment_evidence")
    composite = state.get("composite_assessment")
    evidence_items = state.get("evidence_log", [])

    lines = []
    lines.append("=" * 50)
    lines.append(f"个股预测分析系统 - {intent.stock_name if intent else '股票'} 分析报告")
    lines.append("=" * 50)
    lines.append("")

    if intent:
        lines.append("【用户意图】")
        lines.append(f"股票：{intent.stock_name} ({intent.stock_code})")
        lines.append(f"分析类型：{intent.intent_type} | 周期：{intent.time_horizon}")
        lines.append(f"风险偏好：{intent.risk_preference}")
        lines.append("")

    if market:
        lines.append("【市场结构定位】")
        lines.append(f"当前市场主线：{', '.join(market.current_market_themes)}")
        lines.append(f"股票所属主线：{', '.join(market.stock_themes)}")
        lines.append(f"主线内位置：{market.theme_position}")
        lines.append(f"市场情绪：{market.market_sentiment}")
        lines.append("")

    if route:
        lines.append("【分析范围】")
        lines.append(f"选中的因子：{', '.join(route.sectors)}")
        lines.append(f"分析重点：{route.analysis_focus}")
        lines.append("")

    lines.append("【四大因子分析】")
    for name, ev in [("技术面", tech), ("基本面", fund), ("资金面", cap), ("情绪面", sent)]:
        if ev:
            lines.append(f"  {name}: {ev.trend_signal} (评分: {ev.score}/100)")
            for finding in ev.key_findings:
                lines.append(f"    - {finding}")
            if ev.risk_flags:
                lines.append(f"    风险: {', '.join(ev.risk_flags)}")
        else:
            lines.append(f"  {name}: 未分析")
    lines.append("")

    if composite:
        lines.append("【综合评估】")
        lines.append(f"综合评分：{composite.composite_score}/100")
        lines.append(f"趋势方向：{composite.trend_direction}")
        lines.append(f"位置状态：{composite.position_status}")
        lines.append(f"风险等级：{composite.risk_level}")
        if composite.risk_details:
            lines.append(f"风险详情：{', '.join(composite.risk_details)}")
        lines.append(f"评估摘要：{composite.summary}")
        lines.append("")

    lines.append("【证据记录】")
    for ev in evidence_items:
        lines.append(f"- [{ev.source}] {ev.content[:80]}")
    lines.append("")

    lines.append("=" * 50)
    lines.append("本报告由AI生成，仅供参考，不构成投资建议。")
    lines.append("=" * 50)

    answer_text = "\n".join(lines)
    final = FinalAnswer(answer=answer_text, confidence=0.7 if composite else 0.3)

    log_node_end("final_answer_node", {"answer_length": len(answer_text)})
    return {"final_answer": final, "status": AgentStatus.ANSWERED}


def failure_node(state: AgentState) -> dict:
    """Handle failure states."""
    log_node_start("failure_node")
    error_msg = state.get("error_message") or "Agent execution failed"
    log_error("failure_node", RuntimeError(error_msg))
    log_node_end("failure_node")
    return {"error_message": error_msg, "status": AgentStatus.FAILED}
