"""Small shared helpers: safe attribute access, text/URL utilities, API key lookup.

Gemini responses are read defensively. SDK objects, plain dicts and partially
populated structures are all handled by read_field(), so a small change in
response shape degrades gracefully instead of crashing the app.
"""

from __future__ import annotations

import os
import re
from typing import Any, Iterator
from urllib.parse import urlparse

_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$", re.IGNORECASE
)


# --------------------------------------------------------------------------- #
# Safe access
# --------------------------------------------------------------------------- #
def read_field(obj: Any, name: str, default: Any = None) -> Any:
    """Read name from a dict or object; return default if missing or None."""
    if obj is None:
        return default
    try:
        value = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
    except Exception:
        return default
    return default if value is None else value


def type_of(obj: Any) -> str:
    """Return an object's type field as a lowercase string (enum-safe)."""
    value = read_field(obj, "type", "")
    return str(getattr(value, "value", value) or "").lower()


def iter_text_blocks(interaction: Any) -> Iterator[Any]:
    """Yield every text content block from the model_output steps."""
    for step in read_field(interaction, "steps", []) or []:
        if type_of(step) != "model_output":
            continue
        content = read_field(step, "content", []) or []
        if isinstance(content, str):
            yield {"type": "text", "text": content}
            continue
        for block in content:
            if type_of(block) == "text":
                yield block


def extract_response_text(interaction: Any) -> str:
    """Return the final answer text, or '' if the response has none."""
    try:
        text = read_field(interaction, "output_text")
    except Exception:
        text = None
    if isinstance(text, str) and text.strip():
        return text.strip()
    parts = []
    for block in iter_text_blocks(interaction):
        value = read_field(block, "text")
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return "\n\n".join(parts)


def extract_interaction_id(interaction: Any) -> str | None:
    """Return the interaction id used to continue the conversation."""
    value = read_field(interaction, "id")
    return value if isinstance(value, str) and value else None


# --------------------------------------------------------------------------- #
# Text and URL utilities
# --------------------------------------------------------------------------- #
def truncate(text: str, limit: int) -> str:
    """Collapse whitespace and cut to limit characters with an ellipsis."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 1)].rstrip() + "…"


def md_escape(text: str) -> str:
    """Escape characters that would be interpreted as Markdown."""
    return re.sub(r"([\\`*_\[\]<>])", r"\\\1", text or "")


def plain_label(text: str) -> str:
    """Strip Markdown-significant characters for use in button labels."""
    return re.sub(r"[`*_\[\]<>]", "", text or "").strip()


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def domain_from_url(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def display_domain(title: str | None, url: str) -> str:
    """Best human-readable domain: the citation title if it is a domain, else the URL host."""
    candidate = (title or "").strip().lower()
    if _DOMAIN_RE.match(candidate):
        return candidate[4:] if candidate.startswith("www.") else candidate
    return domain_from_url(url) or candidate


def is_http_url(url: Any) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
def get_api_key() -> str | None:
    """Look up GEMINI_API_KEY in Streamlit secrets, then the environment.

    The key is never logged or displayed. Returns None if it is not configured.
    """
    value: Any = None
    try:
        import streamlit as st

        value = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        value = None  # no secrets file, or running outside Streamlit
    if not value:
        value = os.environ.get("GEMINI_API_KEY")
    value = str(value).strip() if value else ""
    return value or None
