"""Nexa - AI that understands context.

Streamlit entry point. UI only: Gemini access lives in utils/gemini.py,
conversation state in utils/conversation.py, grounding handling in utils/search.py.
"""

from __future__ import annotations

import logging

import streamlit as st
import streamlit.components.v1 as components

from utils import conversation as convo
from utils.gemini import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    DEFAULT_MODEL_LABEL,
    ERROR_MESSAGES,
    NexaError,
    create_client,
    delete_interactions,
    generate_reply,
)
from utils.helpers import get_api_key, plain_label, plural
from utils.prompts import SAMPLE_PROMPTS
from utils.search import format_sources_markdown, why_search_text

logger = logging.getLogger("nexa.app")

MAX_INPUT_CHARS = 6000
USER_AVATAR = ":material/person:"
AI_AVATAR = ":material/auto_awesome:"

MODE_OPTIONS = ["Auto", "Search", "Chat"]
MODE_DESCRIPTIONS = {
    "Auto": "Use current information when needed.",
    "Search": "Research the web for this answer.",
    "Chat": "Answer using conversation context.",
}
STYLE_OPTIONS = ["Concise", "Balanced", "Detailed"]

CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}
.stApp {font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;}
.block-container {max-width: 760px; padding-top: 2rem; padding-bottom: 6rem;}

/* Sidebar */
[data-testid="stSidebar"] {background: #F4F4F1; border-right: 1px solid rgba(0,0,0,0.06);}
[data-testid="stSidebar"] .block-container {padding-top: 1.5rem;}
.nx-brand {font-size: 1.2rem; font-weight: 650; letter-spacing: -0.01em; margin-bottom: 0.9rem;}
.nx-label {font-size: 0.72rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: #8a8a85; margin: 1.1rem 0 0.3rem;}
[data-testid="stSidebar"] .stButton > button[kind="secondary"],
[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-secondary"] {
  width: 100%; justify-content: flex-start; text-align: left; border: none; background: transparent;
  box-shadow: none; padding: 0.4rem 0.6rem; font-weight: 400; border-radius: 8px;
}
[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover,
[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-secondary"]:hover {background: rgba(0,0,0,0.05);}
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] {width: 100%; border-radius: 10px; font-weight: 500;}
[class*="st-key-convactive"] button {background: rgba(0,0,0,0.07) !important; font-weight: 600 !important;}

/* Landing */
.nx-hero {text-align: center; padding: 4rem 0 1.4rem;}
.nx-title {font-size: 2.5rem; font-weight: 650; letter-spacing: -0.03em; line-height: 1.1;}
.nx-tag {font-size: 1.1rem; color: #4a5160; margin-top: 0.4rem;}
.nx-sub {font-size: 0.98rem; color: #8a8a85; margin: 0.9rem auto 0; max-width: 30rem;}
.nx-center {text-align: center;}
.st-key-samples .stButton > button {
  width: 100%; justify-content: flex-start; text-align: left; background: #fff;
  border: 1px solid rgba(0,0,0,0.09); border-radius: 12px; padding: 0.65rem 0.9rem; font-weight: 400; box-shadow: none;
}
.st-key-samples .stButton > button:hover {border-color: rgba(47,79,184,0.5); background: #fafbff;}
.nx-caps {display: flex; flex-wrap: wrap; gap: 1.4rem; justify-content: center; margin-top: 2.2rem;}
.nx-caps div {max-width: 11.5rem; text-align: center;}
.nx-caps strong {display: block; font-size: 0.82rem; font-weight: 600; color: #3b4150;}
.nx-caps span {font-size: 0.78rem; color: #8a8a85;}

/* Conversation */
[data-testid="stChatMessage"] {background: transparent; padding: 0.7rem 0; gap: 0.8rem;}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  background: #F4F4F1; border-radius: 14px; padding: 0.75rem 1rem;
}
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li {line-height: 1.65;}
.nx-meta {font-size: 0.8rem; color: #8a8a85; margin-bottom: 0.4rem;}
.nx-pill {display: inline-block; font-size: 0.74rem; color: #2F4FB8; background: rgba(47,79,184,0.08); border-radius: 999px; padding: 0.12rem 0.6rem; margin: 0.2rem 0 0.4rem;}
.nx-note {font-size: 0.92rem; color: #7a4b00; background: #FFF8E8; border: 1px solid #F3E2B8; border-radius: 10px; padding: 0.6rem 0.85rem;}
[data-testid="stExpander"] {border: none; background: transparent;}
[data-testid="stExpander"] summary {font-size: 0.85rem; color: #5b6272; padding-left: 0;}
[data-testid="stChatInput"] {border-radius: 14px;}
</style>
"""

CAPABILITIES_HTML = (
    '<div class="nx-caps">'
    "<div><strong>Conversation memory</strong><span>Follow-ups build on what came before.</span></div>"
    "<div><strong>Current information</strong><span>Searches the web when it helps.</span></div>"
    "<div><strong>Context-aware answers</strong><span>Shaped by the whole conversation.</span></div>"
    "</div>"
)


# --------------------------------------------------------------------------- #
# Resources and callbacks
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner=False)
def get_client(api_key: str):
    """One shared Gemini client (stateless HTTP; conversation state is per session)."""
    return create_client(api_key)


def _queue_prompt(text: str) -> None:
    st.session_state["pending_prompt"] = text


def _on_new_conversation() -> None:
    st.session_state.pop("pending_prompt", None)
    convo.new_conversation()


def _on_switch(conversation_id: str) -> None:
    st.session_state.pop("pending_prompt", None)
    convo.switch_conversation(conversation_id)


def _on_clear() -> None:
    conv = convo.get_active()
    if conv is not None:
        st.session_state["_to_delete"] = convo.clear_conversation(conv)
    st.session_state.pop("pending_prompt", None)


def _on_retry() -> None:
    conv = convo.get_active()
    if conv is not None:
        text = convo.pop_for_retry(conv)
        if text:
            st.session_state["pending_prompt"] = text


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #
def render_setup() -> None:
    st.markdown(
        '<div class="nx-hero"><div class="nx-title">Nexa</div>'
        '<div class="nx-tag">AI that understands context.</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="nx-center"><strong>Connect your Gemini API key to start using Nexa.</strong></div>',
        unsafe_allow_html=True,
    )
    st.write("")
    st.code('GEMINI_API_KEY = "your-api-key"', language="toml")
    st.caption(
        "Locally, add this line to .streamlit/secrets.toml. On Streamlit Community Cloud, "
        "paste it under App settings → Secrets. You can create a key in Google AI Studio "
        "(aistudio.google.com/apikey)."
    )


def render_sidebar(conv: dict) -> None:
    with st.sidebar:
        st.markdown('<div class="nx-brand">Nexa</div>', unsafe_allow_html=True)
        st.button(
            "New conversation",
            key="new_conv",
            type="primary",
            icon=":material/add:",
            on_click=_on_new_conversation,
        )

        st.markdown('<div class="nx-label">Recent</div>', unsafe_allow_html=True)
        recent = convo.recent_conversations()
        if not recent:
            st.caption("Your conversations will appear here.")
        for item in recent:
            active = item["id"] == conv["id"]
            st.button(
                plain_label(item["title"]) or convo.DEFAULT_TITLE,
                key=f"{'convactive' if active else 'conv'}_{item['id']}",
                on_click=_on_switch,
                args=(item["id"],),
            )

        st.markdown('<div class="nx-label">Mode</div>', unsafe_allow_html=True)
        mode_label = st.radio(
            "Mode", MODE_OPTIONS, key="mode_label", horizontal=True, label_visibility="collapsed"
        )
        st.caption(MODE_DESCRIPTIONS.get(mode_label, ""))

        with st.expander("Settings"):
            st.selectbox("Model", list(AVAILABLE_MODELS), key="model_label")
            st.radio("Response style", STYLE_OPTIONS, key="style_label")

        st.button(
            "Clear conversation",
            key="clear_conv",
            icon=":material/delete_sweep:",
            on_click=_on_clear,
            disabled=not conv["messages"],
        )


def render_landing() -> None:
    st.markdown(
        '<div class="nx-hero"><div class="nx-title">Nexa</div>'
        '<div class="nx-tag">AI that understands context.</div>'
        '<p class="nx-sub">Ask questions, explore ideas, or research what\'s happening right now.</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="nx-center nx-meta">Start a conversation with Nexa.</div>',
        unsafe_allow_html=True,
    )
    with st.container(key="samples"):
        columns = st.columns(2)
        for index, prompt in enumerate(SAMPLE_PROMPTS):
            with columns[index % 2]:
                st.button(prompt, key=f"sample_{index}", on_click=_queue_prompt, args=(prompt,))
    st.markdown(CAPABILITIES_HTML, unsafe_allow_html=True)


def render_suggestions(html: str) -> None:
    """Show Google's search-suggestions widget exactly as returned (grounding terms)."""
    try:
        components.html(html, height=80, scrolling=True)
    except Exception:  # noqa: BLE001
        logger.info("Could not render search suggestions")


def render_assistant(msg: dict) -> None:
    if msg.get("error"):
        st.markdown(f'<div class="nx-note">{msg["content"]}</div>', unsafe_allow_html=True)
        return

    st.markdown(msg["content"])
    search = msg.get("search") or {}

    if search.get("used"):
        st.markdown('<span class="nx-pill">Web research used</span>', unsafe_allow_html=True)
        sources = search.get("sources") or []
        suggestions = search.get("suggestions_html")
        if sources or suggestions:
            label = f"Sources ({len(sources)})" if sources else "Search suggestions"
            with st.expander(label):
                if sources:
                    st.markdown(format_sources_markdown(sources))
                if suggestions:
                    st.caption("Related searches")
                    render_suggestions(suggestions)
        else:
            st.caption("The search ran, but no citable sources were returned.")
        with st.expander("Why current information was used"):
            st.markdown(why_search_text(msg.get("mode", "auto"), search.get("queries")))
    elif msg.get("mode") == "search":
        st.caption("No current sources were used for this response.")


def render_history(conv: dict) -> None:
    for msg in conv["messages"]:
        if msg["role"] == "user":
            with st.chat_message("user", avatar=USER_AVATAR):
                st.markdown(msg["content"])
        else:
            with st.chat_message("assistant", avatar=AI_AVATAR):
                render_assistant(msg)


def render_meta(conv: dict) -> None:
    parts = [f"{plural(convo.message_count(conv), 'message')} in conversation"]
    if convo.used_search(conv):
        parts.append("Web research used")
    st.markdown(f'<div class="nx-meta">{" · ".join(parts)}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Answering a turn
# --------------------------------------------------------------------------- #
def answer(conv: dict, client, prompt: str) -> None:
    ss = st.session_state
    mode = ss.get("mode_label", "Auto").lower()
    style = ss.get("style_label", "Balanced").lower()
    model = AVAILABLE_MODELS.get(ss.get("model_label", DEFAULT_MODEL_LABEL), DEFAULT_MODEL)

    spinner_text = {
        "search": "Researching current information…",
        "auto": "Thinking, and checking the web if needed…",
    }.get(mode, "Thinking…")

    with st.chat_message("assistant", avatar=AI_AVATAR):
        try:
            with st.spinner(spinner_text):
                reply = generate_reply(
                    client,
                    prompt=prompt,
                    model=model,
                    mode=mode,
                    style=style,
                    previous_interaction_id=conv.get("interaction_id"),
                )
        except NexaError as err:
            if err.kind == "state":
                convo.reset_interaction(conv)
            convo.add_error_message(conv, err.user_message, err.kind)
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected failure while answering")
            convo.add_error_message(conv, ERROR_MESSAGES["unknown"], "unknown")
        else:
            convo.add_assistant_message(
                conv,
                reply.text,
                interaction_id=reply.interaction_id,
                search=reply.search.to_dict(),
                mode=mode,
                model=model,
            )
    st.rerun()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(
        page_title="Nexa",
        page_icon=":material/auto_awesome:",
        layout="centered",
        initial_sidebar_state="auto",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    ss = st.session_state
    ss.setdefault("mode_label", "Auto")
    ss.setdefault("model_label", DEFAULT_MODEL_LABEL)
    ss.setdefault("style_label", "Balanced")
    convo.init_state()

    api_key = get_api_key()
    if not api_key:
        render_setup()
        return

    try:
        client = get_client(api_key)
    except NexaError as err:
        st.markdown(f'<div class="nx-note">{err.user_message}</div>', unsafe_allow_html=True)
        return

    conv = convo.get_active()
    render_sidebar(conv)
    conv = convo.get_active()  # callbacks may have changed it

    pending = ss.pop("pending_prompt", None)
    prompt = st.chat_input("What would you like to know?", disabled=bool(pending))

    if pending:
        convo.add_user_message(conv, pending)

    if not conv["messages"]:
        render_landing()
    else:
        render_meta(conv)
        render_history(conv)

    if pending:
        answer(conv, client, pending)  # ends with st.rerun()
    elif convo.can_retry(conv):
        st.markdown(
            '<div class="nx-meta">Nexa did not finish this answer.</div>', unsafe_allow_html=True
        )
        st.button("Try again", key="retry", on_click=_on_retry)

    if prompt is not None:
        text = prompt.strip()
        if not text:
            st.toast("Type a message to send.")
        elif len(text) > MAX_INPUT_CHARS:
            st.toast(f"Please keep messages under {MAX_INPUT_CHARS:,} characters.")
        else:
            ss["pending_prompt"] = text
            st.rerun()

    stale_ids = ss.pop("_to_delete", None)
    if stale_ids:
        delete_interactions(client, stale_ids)


main()
