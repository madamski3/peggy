"""Chat router -- the agent's single HTTP endpoint.

POST /api/chat/ is the only way to interact with the agent. The router
is intentionally thin -- it just validates the request and delegates
everything to the orchestrator's run_agent_loop().
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator import run_agent_loop
from app.database import get_db
from app.schemas.agent import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Send a message to the AI assistant and get a response.

    The agent will:
    1. Assemble relevant context (profile, todos, etc.)
    2. Call Claude with tool definitions
    3. Execute any tool calls (create todos, query data, etc.)
    4. Return a structured response with spoken_summary and actions taken

    For HIGH_STAKES actions, the response will include `confirmation_required`.
    Re-send with the `confirmation_id` to approve and execute.
    """
    return await run_agent_loop(
        user_message=request.message,
        session_id=request.session_id,
        db=db,
        confirmation_id=request.confirmation_id,
    )
