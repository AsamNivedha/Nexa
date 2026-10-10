"""Gemini integration for Nexa (no Streamlit imports).

Uses the current google-genai SDK and the Interactions API:

    client.interactions.create(
        model=..., input=..., previous_interaction_id=..., tools=[...],
        system_instruction=...,
    )

Memory comes from previous_interaction_id: the server restores earlier turns,
so Nexa only sends the new message. tools and system_instruction are
interaction-scoped, so they are re-sent on every call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from google import genai
from google.genai import types

from .helpers import extract_interaction_id, extract_response_text, read_field
from .prompts import build_system_instruction
from .search import SearchInfo, extract_search_info, google_search_tools

logger = logging.getLogger("nexa.gemini")

# Model ids come from Google's Interactions API model list. If Google retires
# one, edit this mapping; the app reads it for the Settings selector.
AVAILABLE_MODELS: dict[str, str] = {
    "Gemini 3.8 Flash": "gemini-3.8-flash",
    "Gemini 3.5 Flash-Lite": "gemini-3.5-flash-lite",
    "Gemini 3.1 Pro Preview": "gemini-3.1-pro-preview",
}
DEFAULT_MODEL_LABEL = "Gemini 3.8 Flash"
DEFAULT_MODEL = AVAILABLE_MODELS[DEFAULT_MODEL_LABEL]

REQUEST_TIMEOUT_MS = 90_000

ERROR_MESSAGES = {
    "config": "Nexa couldn't start the Gemini client. Check your API key configuration.",
    "auth": "Gemini rejected the request. Check that your API key is valid and has access to this model.",
    "rate_limit": "Nexa has reached the Gemini usage limit for now. Wait a moment and try again.",
    "network": "Nexa couldn't reach Gemini. Check your connection and try again.",
    "model": "The selected model isn't available for this key. Choose a different model in Settings.",
    "state": (
        "Nexa couldn't restore the earlier context for this conversation. "
        "Your next message will start with fresh context, or you can start a new conversation."
    ),
    "search": "Current web information could not be retrieved. You can try again or switch to Chat mode.",
    "server": "Gemini could not process this request right now. Please try again shortly.",
    "empty": "Gemini returned an empty response. Try rephrasing your question.",
    "unknown": "Gemini could not process this request right now.",
}


class NexaError(Exception):
    """A user-presentable failure. kind selects the message and UI behavior."""

    def _init_(self, kind: str, user_message: str | None = None) -> None:
        self.kind = kind
        self.user_message = user_message or ERROR_MESSAGES.get(kind, ERROR_MESSAGES["unknown"])
        super()._init_(self.user_message)


@dataclass
class Reply:
    text: str
    interaction_id: str | None
    search: SearchInfo


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
def create_client(api_key: str) -> genai.Client:
    """Create a Gemini client. The key is never logged."""
    if not api_key:
        raise NexaError("config")
    try:
        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Client creation failed: %s", type(exc)._name_)
        raise NexaError("config") from exc


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
def generate_reply(
    client: genai.Client,
    *,
    prompt: str,
    model: str,
    mode: str,
    style: str,
    previous_interaction_id: str | None = None,
) -> Reply:
    """Send one user turn and return Nexa's reply plus grounding information.

    mode: "auto"   -> Google Search enabled, the model decides whether to use it
          "search" -> Google Search enabled and the model is told to research
          "chat"   -> no search tool
    """
    mode = (mode or "auto").lower()
    searching = mode in ("auto", "search")

    request: dict[str, Any] = {
        "model": model or DEFAULT_MODEL,
        "input": prompt,
        "system_instruction": build_system_instruction(style, mode),
    }
    if previous_interaction_id:
        request["previous_interaction_id"] = previous_interaction_id
    if searching:
        request["tools"] = google_search_tools()

    try:
        interaction = client.interactions.create(**request)
    except Exception as exc:  # noqa: BLE001
        raise classify_error(
            exc, searching=searching, has_state=bool(previous_interaction_id)
        ) from exc

    status = str(
        getattr(read_field(interaction, "status", ""), "value", read_field(interaction, "status", ""))
    ).lower()
    if status in {"failed", "cancelled", "canceled", "incomplete"}:
        logger.warning("Interaction ended with status %s", status)
        raise NexaError("search" if searching else "server")

    text = extract_response_text(interaction)
    if not text:
        raise NexaError("empty")

    interaction_id = extract_interaction_id(interaction)
    if not interaction_id:
        logger.warning("Response had no interaction id; follow-ups may lose context.")

    try:
        search = extract_search_info(interaction)
    except Exception:  # noqa: BLE001
        logger.exception("Could not parse grounding metadata")
        search = SearchInfo()

    return Reply(text=text, interaction_id=interaction_id, search=search)


def delete_interactions(client: genai.Client, interaction_ids: list[str]) -> None:
    """Best-effort removal of stored interactions (used by 'Clear conversation')."""
    for interaction_id in interaction_ids:
        try:
            client.interactions.delete(interaction_id)
        except Exception as exc:  # noqa: BLE001
            logger.info("Could not delete a stored interaction: %s", type(exc)._name_)


# --------------------------------------------------------------------------- #
# Error classification
# --------------------------------------------------------------------------- #
_NETWORK_HINTS = ("connect", "timeout", "network", "dns", "ssl", "remoteprotocol", "readerror")


def _status_code(exc: Exception) -> int | None:
    for name in ("status_code", "code", "http_status"):
        value = getattr(exc, name, None)
        if isinstance(value, int):
            return value
    value = getattr(getattr(exc, "response", None), "status_code", None)
    return value if isinstance(value, int) else None


def _is_network_error(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    names = " ".join(cls._name.lower() for cls in type(exc).mro_)
    return any(hint in names for hint in _NETWORK_HINTS)


def classify_error(exc: Exception, *, searching: bool, has_state: bool) -> NexaError:
    """Map any SDK/network exception to a friendly NexaError.

    Classification uses status codes and message text rather than SDK exception
    classes, so it keeps working if the SDK reorganizes its error types.
    """
    if isinstance(exc, NexaError):
        return exc

    code = _status_code(exc)
    text = str(exc).lower()
    logger.warning("Gemini request failed: %s (status=%s)", type(exc)._name_, code)

    if code == 429 or any(w in text for w in ("resource_exhausted", "quota", "rate limit")):
        return NexaError("rate_limit")
    if code in (401, 403) or any(
        w in text
        for w in ("api key not valid", "api_key_invalid", "invalid api key", "permission_denied")
    ):
        return NexaError("auth")
    if has_state and (
        "previous_interaction" in text
        or (
            "interaction" in text
            and any(w in text for w in ("not found", "expired", "does not exist", "invalid"))
        )
    ):
        return NexaError("state")
    if "model" in text and (
        code == 404
        or any(
            w in text
            for w in ("not found", "not supported", "unsupported", "not available", "does not exist")
        )
    ):
        return NexaError("model")
    if _is_network_error(exc):
        return NexaError("network")
    if searching and any(w in text for w in ("google_search", "grounding", "search")):
        return NexaError("search")
    if code is not None and code >= 500:
        return NexaError("server")
    if searching:
        return NexaError(
            "unknown",
            ERROR_MESSAGES["unknown"] + " If it keeps happening, try Chat mode.",
        )
    return NexaError("unknown")
