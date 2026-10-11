"""Gemini REST client (server-side only). The API key is sent in a header and never appears in errors or logs."""
import json
import logging
import re
import time

import httpx

from .config import settings

log = logging.getLogger("ai")
BASE = "https://generativelanguage.googleapis.com/v1beta/models"
FALLBACK_MODEL = "gemini-flash-latest"


class AIError(Exception):
    """Message is safe to show to users."""


def configured() -> bool:
    return bool(settings.gemini_api_key)


def _post(model: str, body: dict) -> httpx.Response:
    last = None
    for attempt in range(3):
        try:
            r = httpx.post(f"{BASE}/{model}:generateContent", headers={"x-goog-api-key": settings.gemini_api_key, "content-type": "application/json"},
                           json=body, timeout=90)
        except httpx.HTTPError as e:
            last = AIError("Could not reach the AI service. Try again in a moment.")
            log.warning("gemini network error: %s", type(e).__name__)
        else:
            if r.status_code in (429, 500, 502, 503, 504):
                last = AIError("The AI service is busy. Try again in a moment.")
                log.warning("gemini status %s", r.status_code)
            else:
                return r
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    raise last


def _call(system: str, contents: list[dict], *, json_mode: bool, max_tokens: int, temperature: float) -> str:
    if not configured():
        raise AIError("AI is not configured on this server (GEMINI_API_KEY is missing).")
    cfg = {"temperature": temperature, "maxOutputTokens": max(max_tokens, 8192 if json_mode else 1024)}
    if json_mode:
        cfg["responseMimeType"] = "application/json"
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "generationConfig": cfg}
    r = _post(settings.gemini_model, body)
    if r.status_code == 404 and settings.gemini_model != FALLBACK_MODEL:
        r = _post(FALLBACK_MODEL, body)
    if r.status_code in (400, 401, 403):
        msg = "The AI key was rejected. Check GEMINI_API_KEY." if r.status_code != 400 else "The AI could not process that request."
        raise AIError(msg)
    if r.status_code != 200:
        raise AIError("The AI service returned an error. Try again later.")
    try:
        data = r.json()
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, ValueError):
        reason = (r.json().get("promptFeedback") or {}).get("blockReason") if r.headers.get("content-type", "").startswith("application/json") else None
        raise AIError("The AI declined to answer that." if reason else "The AI returned an empty answer. Try again.")


def parse_json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise AIError("The AI returned an unreadable answer. Try again with a clearer description.")


def generate_json(system: str, user: str, *, max_tokens: int = 8192, temperature: float = 0.3) -> dict:
    out = parse_json(_call(system, [{"role": "user", "parts": [{"text": user}]}], json_mode=True, max_tokens=max_tokens, temperature=temperature))
    if not isinstance(out, dict):
        raise AIError("The AI returned an unexpected answer. Try again.")
    return out


def generate_text(system: str, messages: list[dict], *, max_tokens: int = 1500, temperature: float = 0.5) -> str:
    contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in messages]
    text = _call(system, contents, json_mode=False, max_tokens=max_tokens, temperature=temperature)
    if not text:
        raise AIError("The AI returned an empty answer. Try again.")
    return text
