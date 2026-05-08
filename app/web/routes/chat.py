from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.db.models import User
from app.web.dependencies import get_current_user
from app.web.templates import templates


router = APIRouter()


@router.get("/chat")
async def chat_page(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        request,
        "pages/chat.html",
        {
            "active_page": "chat",
            "current_user": current_user,
        },
    )


@router.post("/chat/models")
async def chat_models(request: Request, current_user: User = Depends(get_current_user)):
    payload = await request.json()
    server_url = _normalize_server_url(payload.get("server_url"))
    if not server_url:
        return JSONResponse({"detail": "Укажите корректный URL сервера Ollama."}, status_code=400)

    try:
        data = await run_in_threadpool(_ollama_get_json, f"{server_url}/api/tags", 8)
    except OllamaProxyError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=502)

    models = [
        {
            "name": model.get("name", ""),
            "modified_at": model.get("modified_at", ""),
            "size": model.get("size", 0),
        }
        for model in data.get("models", [])
        if model.get("name")
    ]
    return JSONResponse({"models": models})


@router.post("/chat/message")
async def chat_message(request: Request, current_user: User = Depends(get_current_user)):
    payload = await request.json()
    server_url = _normalize_server_url(payload.get("server_url"))
    model = str(payload.get("model") or "").strip()
    messages = _normalize_messages(payload.get("messages"))

    if not server_url:
        return JSONResponse({"detail": "Укажите корректный URL сервера Ollama."}, status_code=400)
    if not model:
        return JSONResponse({"detail": "Выберите модель Ollama."}, status_code=400)
    if not messages:
        return JSONResponse({"detail": "Сообщение не может быть пустым."}, status_code=400)

    try:
        data = await run_in_threadpool(
            _ollama_post_json,
            f"{server_url}/api/chat",
            {"model": model, "messages": messages, "stream": False},
            120,
        )
    except OllamaProxyError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=502)

    answer = data.get("message", {}).get("content") or data.get("response") or ""
    return JSONResponse({"message": answer, "model": data.get("model", model), "done": data.get("done", True)})


class OllamaProxyError(RuntimeError):
    pass


def _normalize_server_url(value: Any) -> str | None:
    raw = str(value or "").strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.username or parsed.password:
        return None
    return raw


def _normalize_messages(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    messages: list[dict[str, str]] = []
    for item in value[-30:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role in {"system", "user", "assistant"} and content:
            messages.append({"role": role, "content": content[:12000]})
    return messages


def _ollama_get_json(url: str, timeout: int) -> dict[str, Any]:
    request = UrlRequest(url, headers={"Accept": "application/json"}, method="GET")
    return _open_json(request, timeout)


def _ollama_post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = UrlRequest(
        url,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    return _open_json(request, timeout)


def _open_json(request: UrlRequest, timeout: int) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = exc.reason
        try:
            error_payload = json.loads(exc.read().decode("utf-8"))
            detail = error_payload.get("error") or error_payload.get("detail") or detail
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        raise OllamaProxyError(f"Ollama вернул ошибку: {detail}") from exc
    except URLError as exc:
        raise OllamaProxyError(f"Не удалось подключиться к Ollama: {exc.reason}") from exc
    except TimeoutError as exc:
        raise OllamaProxyError("Ollama не ответил за отведенное время.") from exc

    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OllamaProxyError("Ollama вернул некорректный JSON.") from exc
