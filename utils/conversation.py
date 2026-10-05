"""Conversation state for Nexa (session-only, no database).

Each conversation is a plain dict stored in st.session_state:

    {
        "id": "a1b2c3d4",
        "title": "Learning RAG",
        "messages": [ {role, content, ...}, ... ],   # what the UI displays
        "interaction_id": "...",                      # Gemini conversation state
        "interaction_ids": ["...", ...],              # every id created, for cleanup
    }

The Gemini interaction_id is what gives Nexa memory: it is passed as
previous_interaction_id on the next turn, so the server restores the history.
Each conversation keeps its own id, which is why switching conversations
restores the right context.
"""

from _future_ import annotations

import time
import uuid
from typing import Any

import streamlit as st

from .helpers import truncate

DEFAULT_TITLE = "New conversation"
MAX_TITLE_CHARS = 38


# --------------------------------------------------------------------------- #
# Setup and lookup
# --------------------------------------------------------------------------- #
def init_state() -> None:
    """Create the session containers once; safe to call on every rerun."""
    ss = st.session_state
    ss.setdefault("conversations", {})
    ss.setdefault("conversation_order", [])
    ss.setdefault("active_id", None)
    if get_active() is None:
        new_conversation()


def get_active() -> dict[str, Any] | None:
    ss = st.session_state
    return ss.get("conversations", {}).get(ss.get("active_id"))


def recent_conversations() -> list[dict[str, Any]]:
    """Non-empty conversations, newest first."""
    ss = st.session_state
    items = [ss["conversations"].get(cid) for cid in ss["conversation_order"]]
    return [c for c in items if c and c["messages"]]


# --------------------------------------------------------------------------- #
# Create / switch / clear
# --------------------------------------------------------------------------- #
def new_conversation() -> dict[str, Any]:
    """Start a fresh conversation (reuses the active one if it is still empty)."""
    active = get_active()
    if active is not None and not active["messages"]:
        return active
    ss = st.session_state
    conv = {
        "id": uuid.uuid4().hex[:8],
        "title": DEFAULT_TITLE,
        "messages": [],
        "interaction_id": None,
        "interaction_ids": [],
        "created": time.time(),
    }
    ss["conversations"][conv["id"]] = conv
    ss["conversation_order"].insert(0, conv["id"])
    ss["active_id"] = conv["id"]
    return conv


def switch_conversation(conversation_id: str) -> None:
    if conversation_id in st.session_state["conversations"]:
        st.session_state["active_id"] = conversation_id


def clear_conversation(conv: dict[str, Any]) -> list[str]:
    """Reset a conversation and return its Gemini interaction ids for cleanup."""
    stale_ids = list(conv.get("interaction_ids", []))
    conv["messages"] = []
    conv["interaction_id"] = None
    conv["interaction_ids"] = []
    conv["title"] = DEFAULT_TITLE
    return stale_ids


def reset_interaction(conv: dict[str, Any]) -> None:
    """Forget the Gemini state pointer (used when the server can't restore it)."""
    conv["interaction_id"] = None


# --------------------------------------------------------------------------- #
# Messages
# --------------------------------------------------------------------------- #
def make_title(text: str) -> str:
    return truncate(text, MAX_TITLE_CHARS) or DEFAULT_TITLE


def add_user_message(conv: dict[str, Any], text: str) -> None:
    conv["messages"].append({"role": "user", "content": text})
    if conv["title"] == DEFAULT_TITLE:
        conv["title"] = make_title(text)


def add_assistant_message(
    conv: dict[str, Any],
    text: str,
    *,
    interaction_id: str | None,
    search: dict[str, Any] | None,
    mode: str,
    model: str,
) -> None:
    conv["messages"].append(
        {
            "role": "assistant",
            "content": text,
            "search": search,
            "mode": mode,
            "model": model,
        }
    )
    if interaction_id:
        conv["interaction_id"] = interaction_id
        conv["interaction_ids"].append(interaction_id)


def add_error_message(conv: dict[str, Any], text: str, kind: str) -> None:
    """Errors are shown in the thread but never counted or sent to Gemini."""
    conv["messages"].append(
        {"role": "assistant", "content": text, "error": True, "kind": kind}
    )


def message_count(conv: dict[str, Any]) -> int:
    return sum(1 for m in conv["messages"] if not m.get("error"))


def used_search(conv: dict[str, Any]) -> bool:
    return any(
        (m.get("search") or {}).get("used")
        for m in conv["messages"]
        if m["role"] == "assistant"
    )


# --------------------------------------------------------------------------- #
# Retry
# --------------------------------------------------------------------------- #
def can_retry(conv: dict[str, Any]) -> bool:
    """True if the last turn failed or was interrupted before Nexa answered."""
    messages = conv["messages"]
    if not messages:
        return False
    last = messages[-1]
    return bool(last.get("error")) or last["role"] == "user"


def pop_for_retry(conv: dict[str, Any]) -> str | None:
    """Remove the failed turn and return the user's text so it can be re-sent."""
    messages = conv["messages"]
    while messages and messages[-1].get("error"):
        messages.pop()
    if messages and messages[-1]["role"] == "user":
        return messages.pop()["content"]
    return None
