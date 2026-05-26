from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.agents.graph import CommerceAgentGraph
from backend.agents.langgraph_adapter import LANGGRAPH_AVAILABLE
from backend.data_loader import DEFAULT_DATA_DIR
from backend.models import AgentResponse


class CommerceAgent:
    """Public facade for the LangGraph-powered shopping workflow."""

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.graph = CommerceAgentGraph(self.data_dir)

    def run(
        self,
        query: str,
        user_id: str = "demo-user",
        require_confirmation: bool = False,
        use_llm: bool = False,
        brief_overrides: dict[str, Any] | None = None,
        human_feedback: str | None = None,
    ) -> AgentResponse:
        state = self.graph.invoke(
            {
                "query": query,
                "user_id": user_id,
                "require_confirmation": require_confirmation,
                "use_llm": use_llm,
                "brief_overrides": brief_overrides,
                "human_feedback": human_feedback,
                "trace": [],
                "workflow_status": "started",
            }
        )
        return AgentResponse(
            query=query,
            answer=state.get("answer", ""),
            intent=state.get("intent", {}),
            purchase_brief=state.get("purchase_brief", {}),
            comparison_table=state.get("comparison_table", []),
            recommendations=state.get("recommendations", []),
            trace=state.get("trace", []),
            self_check=state.get("self_check", {}),
            memory_update=state.get("memory_update", {}),
            llm_meta=state.get("llm_meta", {}),
            workflow_status=state.get("workflow_status", "unknown"),
        )

    @property
    def uses_real_langgraph(self) -> bool:
        return LANGGRAPH_AVAILABLE
