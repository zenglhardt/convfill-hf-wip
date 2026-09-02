"""Local host for the Hugging Face realtime voice interface.

The speech pipeline is a separate ``speech-to-speech serve`` process. This app
only serves the browser UI, publishes its loopback realtime URL, and keeps an
optional Serper key on the server side.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
SPEECH_TO_SPEECH_URL = os.environ.get(
    "SPEECH_TO_SPEECH_URL", "ws://127.0.0.1:8765/v1/realtime"
).strip()
STARTUP_GREETING = os.environ.get("STARTUP_GREETING", "").strip()
SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "").strip()
SERPER_URL = "https://google.serper.dev/search"
MAX_RESULTS = 5

logger = logging.getLogger("convfill.speech_demo")
app = FastAPI(title="ConvFill Hugging Face Voice Demo")


class SearchRequest(BaseModel):
    query: str
    key: str | None = None


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def config() -> dict[str, object]:
    return {
        "search": bool(SERPER_API_KEY),
        "lb": False,
        "allowDirect": True,
        "s2sUrl": SPEECH_TO_SPEECH_URL,
        "rtc": False,
        "iceServers": [],
        "startupGreeting": STARTUP_GREETING,
        "auth": False,
    }


@app.get("/api/me")
def me() -> dict[str, bool]:
    return {"enabled": False}


@app.get("/vendor/openai-realtime-agents.umd.js", include_in_schema=False)
def agents_sdk_bundle() -> FileResponse:
    path = (
        HERE
        / "node_modules"
        / "@openai"
        / "agents-realtime"
        / "dist"
        / "bundle"
        / "openai-realtime-agents.umd.js"
    )
    if not path.is_file():
        raise HTTPException(
            status_code=503,
            detail="Browser dependencies are missing; run npm ci in web_demo/hf_interface.",
        )
    return FileResponse(path, media_type="text/javascript")


@app.post("/api/search")
async def search(req: SearchRequest) -> JSONResponse:
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Empty query.")
    key = (req.key or "").strip() or SERPER_API_KEY
    if not key:
        raise HTTPException(status_code=503, detail="Search is not configured.")

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(
                SERPER_URL,
                headers={"X-API-KEY": key, "Content-Type": "application/json"},
                json={"q": query, "num": MAX_RESULTS},
            )
    except httpx.RequestError as exc:
        logger.warning("Serper unreachable: %r", exc)
        raise HTTPException(status_code=502, detail="Search provider unreachable.") from exc

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Search provider error ({response.status_code}).",
        )

    data = response.json()
    results = [
        {
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
            "url": item.get("link", ""),
        }
        for item in (data.get("organic") or [])[:MAX_RESULTS]
    ]
    answer_box = data.get("answerBox") or {}
    answer = answer_box.get("answer") or answer_box.get("snippet")
    if not answer:
        answer = (data.get("knowledgeGraph") or {}).get("description")
    return JSONResponse({"query": query, "answer": answer, "results": results})


# Registered last so API and vendor routes win.
app.mount("/", StaticFiles(directory=HERE, html=True), name="static")

