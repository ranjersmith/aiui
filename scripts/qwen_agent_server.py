#!/usr/bin/env python3
"""[EXPERIMENTAL] Standalone Qwen-Agent API service.

⚠️  This is an experimental service not integrated with the main aiui pipeline.
    Status: Development/Research only
    Maintainer: Research team
    Use at your own risk in production

Runs a lightweight FastAPI server that wraps qwen-agent and exposes:
- GET /health
- POST /chat
- POST /v1/chat/completions (OpenAI-compatible, non-stream)
"""

from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from qwen_agent.agents import Assistant

DEFAULT_MODEL = os.getenv("QWEN_AGENT_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
DEFAULT_SERVER = os.getenv("QWEN_AGENT_MODEL_SERVER", "http://127.0.0.1:8081/v1")
DEFAULT_API_KEY = os.getenv("QWEN_AGENT_API_KEY", "EMPTY")
DEFAULT_SYSTEM = os.getenv(
    "QWEN_AGENT_SYSTEM",
    "You are a concise assistant. Use clean TeX delimiters for equations.",
)

app = FastAPI(title="qwen-agent-server", version="0.1.0")


class ChatRequest(BaseModel):
    message: str
    model: str | None = None
    system: str | None = None


class OpenAIMessage(BaseModel):
    role: str
    content: Any


class OpenAIChatRequest(BaseModel):
    model: str | None = None
    messages: list[OpenAIMessage] = Field(default_factory=list)
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: list[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                out.append(str(item.get("text", "")))
            else:
                out.append(str(item))
        return "\n".join(out).strip()
    return str(content)


def _build_agent(model: str, system: str) -> Assistant:
    llm_cfg = {
        "model": model,
        "model_server": DEFAULT_SERVER,
        "api_key": DEFAULT_API_KEY,
        "generate_cfg": {
            "top_p": 0.8,
            "temperature": 0.2,
            "max_input_tokens": 12000,
        },
    }
    return Assistant(llm=llm_cfg, function_list=[], system_message=system)


def _run_agent(messages: list[dict[str, Any]], model: str, system: str) -> str:
    bot = _build_agent(model=model, system=system)
    final = list(bot.run(messages=messages))[-1]
    if not final:
        raise RuntimeError("empty response from qwen-agent")
    return _extract_text(final[-1].get("content", ""))


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "qwen-agent",
        "model": DEFAULT_MODEL,
        "model_server": DEFAULT_SERVER,
    }


@app.post("/chat")
def chat(req: ChatRequest) -> dict[str, Any]:
    model = req.model or DEFAULT_MODEL
    system = req.system or DEFAULT_SYSTEM
    try:
        text = _run_agent(messages=[{"role": "user", "content": req.message}], model=model, system=system)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"qwen-agent error: {exc}") from exc

    return {
        "model": model,
        "response": text,
    }


@app.post("/v1/chat/completions")
def chat_completions(req: OpenAIChatRequest) -> dict[str, Any]:
    if req.stream:
        raise HTTPException(status_code=400, detail="stream=true not supported by this lightweight server")

    model = req.model or DEFAULT_MODEL
    system = DEFAULT_SYSTEM
    messages: list[dict[str, Any]] = []

    for msg in req.messages:
        role = str(msg.role or "user")
        content_text = _extract_text(msg.content)
        if role == "system":
            system = content_text or system
            continue
        messages.append({"role": role, "content": content_text})

    if not messages:
        raise HTTPException(status_code=400, detail="at least one non-system message is required")

    started = time.time()
    try:
        answer = _run_agent(messages=messages, model=model, system=system)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"qwen-agent error: {exc}") from exc

    prompt_chars = sum(len(_extract_text(m.content)) for m in req.messages)
    completion_chars = len(answer)

    return {
        "id": f"chatcmpl-qwen-agent-{int(started * 1000)}",
        "object": "chat.completion",
        "created": int(started),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_chars,
            "completion_tokens": completion_chars,
            "total_tokens": prompt_chars + completion_chars,
        },
    }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("QWEN_AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("QWEN_AGENT_PORT", "3312"))
    uvicorn.run(app, host=host, port=port)
