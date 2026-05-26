from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from backend.agents.workflow import CommerceAgent


app = FastAPI(title="CommerceMind-Agent API")
agent = CommerceAgent()


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1)
    user_id: str = "demo-user"
    require_confirmation: bool = False
    use_llm: bool = False
    brief_overrides: dict | None = None
    human_feedback: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    response = agent.run(
        query=request.query,
        user_id=request.user_id,
        require_confirmation=request.require_confirmation,
        use_llm=request.use_llm,
        brief_overrides=request.brief_overrides,
        human_feedback=request.human_feedback,
    )
    return response.to_dict()
