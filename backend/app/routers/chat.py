"""Chat router -- the agent's HTTP endpoints.

POST /api/chat/       -- standard request/response (existing)
POST /api/chat/stream -- SSE endpoint with real-time status updates (new)

The router is intentionally thin -- it validates the request and delegates
everything to the orchestrator's run_agent_loop().
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.orchestrator import run_agent_loop
from app.database import get_db
from app.schemas.agent import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

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


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Send a message and receive real-time status updates via SSE.

    Emits Server-Sent Events as the agent progresses through its loop:
      event: status   -- progress updates ("Checking your calendar...")
      event: complete -- final ChatResponse JSON

    The frontend should fall back to the standard /api/chat/ endpoint
    if the SSE connection fails.
    """
    status_queue: asyncio.Queue[str] = asyncio.Queue()

    async def status_callback(message: str) -> None:
        await status_queue.put(message)

    async def generate():
        # Run the agent loop in a background task so we can stream
        # status updates as they arrive
        loop_task = asyncio.create_task(
            run_agent_loop(
                user_message=request.message,
                session_id=request.session_id,
                db=db,
                confirmation_id=request.confirmation_id,
                status_callback=status_callback,
            )
        )

        try:
            while not loop_task.done():
                # Check for client disconnect
                if await http_request.is_disconnected():
                    loop_task.cancel()
                    return

                try:
                    # Wait for status updates with a short timeout so
                    # we can check if the task completed
                    message = await asyncio.wait_for(
                        status_queue.get(), timeout=0.5,
                    )
                    yield f"event: status\ndata: {json.dumps({'message': message})}\n\n"
                except asyncio.TimeoutError:
                    continue

            # Drain any remaining status messages
            while not status_queue.empty():
                message = status_queue.get_nowait()
                yield f"event: status\ndata: {json.dumps({'message': message})}\n\n"

            # Get the final response
            response: ChatResponse = loop_task.result()
            payload = response.model_dump(mode="json")
            yield f"event: complete\ndata: {json.dumps(payload)}\n\n"

        except asyncio.CancelledError:
            loop_task.cancel()
        except Exception as e:
            logger.exception("SSE stream error")
            error_data = json.dumps({"error": str(e)})
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
