"""
Chat API endpoint — conversational analytics agent.

Streams responses so the user sees tokens as they arrive.
Reuses the same pydantic-ai agent + tools from src/agent/agent.py.
"""

import json
import logging
from datetime import date, timedelta

import psycopg2
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.auth.db import User
from src.auth.manager import current_active_user
from src.config import settings

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """\
You are an expert e-commerce analytics assistant for an Australian online store. \
You have access to tools that query Shopify and Meta Ads data. \
The user will ask questions about their business performance and you should \
answer using real data from their store.

## Rules
- Always query the data using your tools before answering. Never guess or make up numbers.
- All currency is AUD. Display as $X,XXX.XX.
- Be concise and direct. Lead with the key number or finding.
- When comparing periods, show the percentage change.
- If a question is ambiguous about dates, default to the last 30 days.
- If the user asks about trends, use compare_periods to show WoW or period-over-period changes.
- If a tool returns an error (e.g. "No data for this period"), tell the user honestly.
- Keep responses focused and under 300 words unless the user asks for detail.
- Format numbers clearly: use commas for thousands, 2 decimal places for currency.
- You can suggest follow-up questions the user might want to ask.
- Today's date is {today}.
"""


class ChatRequest(BaseModel):
    message: str


@router.post("")
async def chat(
    body: ChatRequest,
    user: User = Depends(current_active_user),
):
    """
    Chat with the analytics agent. Streams the response as SSE.
    """
    if not user.tenant_id:
        raise HTTPException(
            status_code=400,
            detail="Connect Shopify first to chat with your data.",
        )

    tenant_id = user.tenant_id

    async def generate():
        from src.agent.agent import AgentDeps, analytics_agent

        conn = psycopg2.connect(settings.database_url)
        try:
            today = date.today()
            deps = AgentDeps(
                conn=conn,
                tenant_id=tenant_id,
                report_end_date=today,
                report_start_date=today - timedelta(days=30),
            )

            prompt = CHAT_SYSTEM_PROMPT.format(today=today.isoformat())

            async with analytics_agent.run_stream(
                body.message,
                deps=deps,
                instructions=prompt,
            ) as stream:
                async for chunk in stream.stream_text(delta=True):
                    yield f"data: {json.dumps({'type': 'delta', 'content': chunk})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.error("Chat error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        finally:
            conn.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
