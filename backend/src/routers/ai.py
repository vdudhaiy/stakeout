'''
Router for the AI Explanation Layer: a per-stock plain-English insight card,
and a floating chat that's aware of whatever the user is currently looking
at. Both are public (no auth) — consistent with /stocks/{ticker} itself —
and both fail soft (503) if Ollama isn't reachable, since this is a
supplementary feature layered on top of data the rest of the app already
shows without it.
'''

import datetime

from fastapi import APIRouter, HTTPException, Query

from cache import ai_cache
from config import OLLAMA_MODEL
from schemas.ai import ChatRequest, ChatResponse, StockExplanationResponse
from services import analytics_service, llm_service

router = APIRouter(prefix="/ai", tags=["AI"])

_UNAVAILABLE_DETAIL = (
    "AI explanations are unavailable right now — make sure Ollama is running "
    f"locally with the '{OLLAMA_MODEL}' model pulled."
)


@router.get("/stocks/{ticker}/explain", response_model=StockExplanationResponse)
async def explain_stock(ticker: str, refresh: bool = Query(False)):
    '''
    Plain-English summary of a stock's current technicals + recent news,
    generated from facts Stakeout already computed (see analytics_service).
    Cached per-ticker for an hour; pass ?refresh=true to bypass the cache.
    '''
    ticker = ticker.upper()
    cache_key = f"explain:{ticker}"
    if not refresh:
        cached = ai_cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        facts = await analytics_service.build_fact_sheet(ticker)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    summary = await llm_service.generate_explanation(facts)
    if summary is None:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE_DETAIL)

    response = StockExplanationResponse(
        ticker=ticker,
        summary=summary,
        facts=facts,
        confidence=facts["confidence"],
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        model=OLLAMA_MODEL,
    )
    ai_cache.set(cache_key, response)
    return response


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    '''
    One turn of the floating AI chat. `context` tells the backend what the
    user is currently looking at:
    - "stock": facts are recomputed server-side from `context.ticker`, the
      same way /stocks/{ticker}/explain does, so chat and the insight card
      never disagree.
    - "portfolio": `context.facts` is used as-is — already-computed numbers
      the frontend supplied (guest portfolios never reach this backend).
    - "general" / absent: no extra facts are attached.
    '''
    context_facts: dict | None = None
    if payload.context is not None:
        if payload.context.kind == "stock" and payload.context.ticker:
            try:
                context_facts = await analytics_service.build_fact_sheet(payload.context.ticker)
            except ValueError:
                context_facts = None  # ticker not archived — chat still works without it
        elif payload.context.kind == "portfolio":
            context_facts = payload.context.facts

    history = [m.model_dump() for m in payload.history]
    reply = await llm_service.chat(payload.message, context_facts, history)
    if reply is None:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE_DETAIL)
    return ChatResponse(reply=reply)
