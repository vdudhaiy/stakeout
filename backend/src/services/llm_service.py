'''
Thin client for a locally-run Ollama instance, powering the AI Explanation
Layer (per-stock insight card + floating chat).

Design principle: the model never sees raw price ticks, full news bodies, or
anything Stakeout hasn't already computed and could show the user directly.
It only narrates a small, precomputed "facts" dict (see analytics_service.py)
into plain English. Every function here returns None instead of raising on
any failure (connection refused, timeout, malformed response) — Ollama is an
optional local dependency, and callers degrade gracefully rather than
breaking the rest of the app.
'''

from __future__ import annotations

import json
import logging

import httpx

from config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(90.0, connect=5.0)  # CPU-only inference of a 3B model is a real ~20-45s per turn, plus room for a cold model load
_KEEP_ALIVE = "10m"  # keep the model resident between the insight card and chat calls

SYSTEM_PROMPT_EXPLAIN = """You are a financial data explainer inside a retail investing dashboard called Stakeout.

You will be given a JSON object of PRE-COMPUTED facts about one stock: its price, technical indicator values/classifications, and recent news headlines. Rules you must follow:
- Only use the facts in the JSON. Never invent numbers, news, or events that are not present.
- Explain in plain English, for a beginner, what the indicators suggest about the stock's recent behavior.
- Mention both a strength and a weakness/risk when the facts support it.
- If "rsi_recovery" is present, mention the historical recovery rate but explicitly note it is based on a small number of past occurrences and is not a prediction.
- NEVER recommend buying, selling, or holding, and never give a price target. You are explaining data, not giving financial advice.
- Always include a brief note that technical indicators describe the past, not the future.
- Keep it to 3-5 short sentences. No headers, no bullet lists, no markdown.
"""

SYSTEM_PROMPT_CHAT = """You are the Stakeout AI assistant, a floating chat helper on a retail investing dashboard.

Rules you must follow:
- If a "context" JSON object is provided, it contains PRE-COMPUTED facts (indicator values, portfolio numbers) about what the user is currently looking at. Only use numbers from that JSON — never invent prices, indicator values, or news.
- If no context is provided, or the question is unrelated to it, answer generally but say plainly when you don't have specific data on hand rather than guessing.
- NEVER recommend buying, selling, or holding a specific security, and never give a price target or portfolio allocation advice.
- Keep answers short (a few sentences) and conversational. No markdown headers or bullet lists.
- Always leave room for uncertainty — you are explaining data, not predicting markets.
"""

# Defensive second layer: small local models don't always obey the system
# prompt. If output looks like advice anyway, we append a corrective note
# rather than silently trusting the model.
_ADVICE_MARKERS = (
    "you should buy", "you should sell", "i recommend", "i'd recommend",
    "strong buy", "strong sell", "definitely buy", "definitely sell",
    "is a buy", "is a sell", "price target",
)

_ADVICE_DISCLAIMER = (
    " (Note: this is an automated description of indicators, not financial advice or a "
    "recommendation — please treat it only as informational.)"
)


def _looks_like_advice(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _ADVICE_MARKERS)


def _finalize(text: str) -> str:
    text = text.strip()
    if _looks_like_advice(text):
        text += _ADVICE_DISCLAIMER
    return text


async def _chat_completion(messages: list[dict]) -> str | None:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": _KEEP_ALIVE,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
        content = data.get("message", {}).get("content")
        if not content or not content.strip():
            return None
        return _finalize(content)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Ollama request failed (model=%s): %s", OLLAMA_MODEL, e)
        return None


async def generate_explanation(facts: dict) -> str | None:
    '''Turn a stock facts dict (see analytics_service.build_fact_sheet) into a short summary.'''
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_EXPLAIN},
        {"role": "user", "content": json.dumps(facts)},
    ]
    return await _chat_completion(messages)


async def chat(message: str, context_facts: dict | None, history: list[dict]) -> str | None:
    '''
    Open-ended chat turn. `history` is prior {role, content} turns from this
    conversation (frontend-held, not persisted server-side). `context_facts`
    is attached as a synthetic prior turn so the model sees it as data, not
    as something the user typed.
    '''
    messages = [{"role": "system", "content": SYSTEM_PROMPT_CHAT}]
    if context_facts is not None:
        messages.append({"role": "user", "content": f"context: {json.dumps(context_facts)}"})
        messages.append({"role": "assistant", "content": "Got it, I'll use that context if it's relevant."})
    messages.extend(history)
    messages.append({"role": "user", "content": message})
    return await _chat_completion(messages)
