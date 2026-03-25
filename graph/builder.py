"""LangGraph StateGraph builder with conditional routing.

Graph topology:
  orchestrator → market_research → [technical, fundamental, sentiment] (parallel-like)
                → risk → decision

Conditional edges:
  - After risk: if risk=high → decision (skip further analysis)
  - After sentiment: if sentiment missing → re-fetch once
"""

import logging
from langgraph.graph import StateGraph, END

from graph.state import GraphState
from agents.market_agent import market_research_agent
from agents.technical_agent import technical_analysis_agent
from agents.fundamental_agent import fundamental_analysis_agent
from agents.sentiment_agent import sentiment_analysis_agent
from agents.risk_agent import risk_management_agent
from agents.decision_agent import decision_agent
from agents.execution_agent import execution_agent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Orchestrator node — initialises state
# ---------------------------------------------------------------------------

def orchestrator(state: dict) -> dict:
    logger.info(f"[Orchestrator] Starting analysis for {state['ticker']}")
    state.setdefault("logs", [])
    state["logs"].append(f"[Orchestrator] Pipeline started for {state['ticker']}")
    return state

# ---------------------------------------------------------------------------
# Conditional routing functions
# ---------------------------------------------------------------------------

def route_after_sentiment(state: dict) -> str:
    """If sentiment data is missing, retry once; otherwise proceed to risk."""
    sentiment = state.get("sentiment", {})
    if sentiment.get("missing") and not state.get("_sentiment_retried"):
        state["_sentiment_retried"] = True
        return "retry_sentiment"
    return "risk"


def route_after_risk(state: dict) -> str:
    """If risk is high, jump straight to decision (skip further deliberation)."""
    if state.get("risk", {}).get("level") == "high":
        logger.info("[Router] High risk detected — fast-tracking to decision")
        state["logs"].append("[Router] High risk → fast-track to decision")
    return "decision"  # decision agent handles the high-risk case internally

# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    g = StateGraph(GraphState)

    # Add nodes
    g.add_node("orchestrator", orchestrator)
    g.add_node("market_research", market_research_agent)
    g.add_node("technical", technical_analysis_agent)
    g.add_node("fundamental", fundamental_analysis_agent)
    g.add_node("sentiment", sentiment_analysis_agent)
    g.add_node("risk", risk_management_agent)
    g.add_node("decision", decision_agent)
    g.add_node("execution", execution_agent)

    # Linear edges: orchestrator → market → parallel-ish analysis chain
    g.set_entry_point("orchestrator")
    g.add_edge("orchestrator", "market_research")
    g.add_edge("market_research", "technical")
    g.add_edge("technical", "fundamental")
    g.add_edge("fundamental", "sentiment")

    # Conditional: after sentiment → risk (or retry sentiment)
    g.add_conditional_edges("sentiment", route_after_sentiment, {
        "retry_sentiment": "sentiment",
        "risk": "risk",
    })

    # Conditional: after risk → decision
    g.add_conditional_edges("risk", route_after_risk, {
        "decision": "decision",
    })

    g.add_edge("decision", "execution")
    g.add_edge("execution", END)

    return g.compile()
