from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.agents.checkpoints import SQLiteCheckpointStore
from backend.agents.conversation import (
    SQLiteConversationStore,
    answer_followup_from_last_response,
    is_followup_query,
)
from backend.agents.graph import CommerceAgentGraph
from backend.agents.langgraph_adapter import LANGGRAPH_AVAILABLE
from backend.data_loader import DEFAULT_DATA_DIR
from backend.models import AgentResponse, TraceStep
from backend.observability.monitoring import SQLiteRunMonitor


class CommerceAgent:
    """Public facade for the LangGraph-powered shopping workflow."""

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        cache_dir = Path(__file__).resolve().parents[2] / ".cache"
        self.graph = CommerceAgentGraph(self.data_dir)
        self.checkpoints = SQLiteCheckpointStore(cache_dir / "hitl_checkpoints.sqlite")
        self.conversations = SQLiteConversationStore(cache_dir / "conversation.sqlite")
        self.monitor = SQLiteRunMonitor(cache_dir / "run_monitor.sqlite")

    def run(
        self,
        query: str,
        user_id: str = "demo-user",
        require_confirmation: bool = False,
        use_llm: bool = False,
        brief_overrides: dict[str, Any] | None = None,
        human_feedback: str | None = None,
        session_id: str | None = None,
    ) -> AgentResponse:
        run_id = str(uuid4())
        session_id = session_id or user_id
        checkpoint = self.checkpoints.load_pending(session_id)
        effective_query = query
        if checkpoint and (human_feedback or brief_overrides):
            effective_query = str(checkpoint.get("query") or query)

        if is_followup_query(effective_query) and not human_feedback and not brief_overrides:
            followup = self._answer_followup(
                query=effective_query,
                user_id=user_id,
                session_id=session_id,
                run_id=run_id,
            )
            if followup is not None:
                return followup

        state = self.graph.invoke(
            {
                "query": effective_query,
                "user_id": user_id,
                "session_id": session_id,
                "run_id": run_id,
                "require_confirmation": require_confirmation,
                "use_llm": use_llm,
                "brief_overrides": brief_overrides,
                "human_feedback": human_feedback,
                "trace": [],
                "workflow_status": "started",
            }
        )
        response = AgentResponse(
            query=effective_query,
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
            run_id=run_id,
            session_id=session_id,
        )
        if response.workflow_status == "awaiting_user_confirmation":
            self.checkpoints.save_pending(
                session_id,
                {
                    "query": effective_query,
                    "purchase_brief": response.purchase_brief,
                    "intent": response.intent,
                    "run_id": run_id,
                },
            )
        else:
            self.checkpoints.clear(session_id)
            self.conversations.append_turn(
                session_id=session_id,
                query=effective_query,
                response=response.to_dict(),
            )
        self.monitor.record(response.to_dict())
        response.monitoring = self.monitor.metrics()
        return response

    def _answer_followup(
        self,
        query: str,
        user_id: str,
        session_id: str,
        run_id: str,
    ) -> AgentResponse | None:
        last_response = self.conversations.last_response(session_id)
        if not last_response:
            return None
        answer = answer_followup_from_last_response(query, last_response)
        if not answer:
            return None
        response = AgentResponse(
            query=query,
            answer=answer,
            intent=last_response.get("intent", {}),
            purchase_brief=last_response.get("purchase_brief", {}),
            comparison_table=last_response.get("comparison_table", []),
            recommendations=last_response.get("recommendations", []),
            trace=[
                TraceStep(
                    name="Conversation Follow-up",
                    reason="基于同一 session 上一轮推荐结果回答追问",
                    inputs={"query": query, "session_id": session_id},
                    outputs={"answer": answer},
                )
            ],
            self_check={"passed": True, "issues": [], "checked_items": 0},
            memory_update=self.graph.memory.get(user_id),
            llm_meta={"enabled": False, "used": False, "reason": "followup_answer_from_session"},
            workflow_status="followup_answered",
            run_id=run_id,
            session_id=session_id,
        )
        self.conversations.append_turn(
            session_id=session_id,
            query=query,
            response=response.to_dict(),
        )
        self.monitor.record(response.to_dict())
        response.monitoring = self.monitor.metrics()
        return response

    @property
    def uses_real_langgraph(self) -> bool:
        return LANGGRAPH_AVAILABLE
