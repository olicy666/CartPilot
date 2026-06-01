from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from backend.agents.shopping_copilot import ShoppingCopilot
from backend.agents.workflow import CommerceAgent


app = FastAPI(title="CommerceMind-Agent API")
agent = CommerceAgent()
copilot = ShoppingCopilot(agent=agent)


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    user_id: str = "demo-user"
    session_id: str | None = None
    require_confirmation: bool = False
    use_llm: bool = False
    brief_overrides: dict | None = None
    human_feedback: str | None = None


class ShoppingEventRequest(BaseModel):
    session_id: str = "demo-session"
    user_id: str = "demo-user"
    event_type: str = Field(..., min_length=1)
    payload: dict = Field(default_factory=dict)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    response = agent.run(
        query=request.query,
        user_id=request.user_id,
        session_id=request.session_id,
        require_confirmation=request.require_confirmation,
        use_llm=request.use_llm,
        brief_overrides=request.brief_overrides,
        human_feedback=request.human_feedback,
    )
    return response.to_dict()


@app.get("/monitoring/metrics")
def monitoring_metrics() -> dict:
    return agent.monitor.metrics()


@app.get("/monitoring/traces")
def monitoring_traces(limit: int = 20) -> list[dict]:
    return agent.monitor.recent_traces(limit=limit)


@app.get("/sessions/{session_id}/checkpoint")
def session_checkpoint(session_id: str) -> dict:
    checkpoint = agent.checkpoints.load_pending(session_id)
    return checkpoint or {}


@app.post("/shopping/events")
def shopping_event(request: ShoppingEventRequest) -> dict:
    return copilot.handle_event(request.model_dump())


@app.get("/shopping/sessions/{session_id}")
def shopping_session_state(session_id: str) -> dict:
    return copilot.get_state(session_id)
