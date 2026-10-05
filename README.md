# Nexa

*AI that understands context.*

Nexa is a context-aware AI research assistant built with Python, Streamlit and the Gemini API. It keeps the thread of a conversation, answers follow-up questions in context, and uses Gemini's Google Search grounding when a question depends on current information, showing the sources it used.

## 1. Overview

Nexa combines three ideas in one small, cohesive app:

> Conversation memory + current information + Gemini intelligence.

## 2. Product purpose

Most chat demos either forget what was said or confidently answer questions about the present from stale training data. Nexa addresses both: follow-ups like "How is that different from fine-tuning?" resolve against earlier turns, and time-sensitive questions are grounded in live web results with visible sources.

## 3. Core features

- Multi-turn conversations with server-side memory
- Three modes: *Auto* (search when useful), *Search* (always research), *Chat* (no web search)
- Google Search grounding with a clean, deduplicated source list showing what each source supports
- "Web research used" indicator and a "Why current information was used" explanation
- Session-based conversation list, New conversation and Clear conversation
- Response styles (Concise / Balanced / Detailed) and a model selector
- Friendly error handling and a retry action; no raw tracebacks in the UI

## 4. How conversation memory works

Nexa uses the Gemini *Interactions API*. Every response has an id. Nexa stores that id in st.session_state per conversation and sends it as previous_interaction_id on the next turn. The server restores the earlier turns, so Nexa sends only the new message instead of rebuilding a growing prompt.

- Each conversation keeps its own interaction id, so switching conversations restores the right context.
- system_instruction and tools are interaction-scoped in the API, so Nexa re-sends them on every turn.
- Interactions are stored by Google (store=true is the default): about *55 days on the paid tier, 1 day on the free tier*. On the free tier an old conversation can therefore lose its server-side context. If Gemini can't restore it, Nexa says so and the next message starts with fresh context.
- "Clear conversation" resets local state and makes a best-effort call to delete the stored interactions.

## 5. How Gemini integration works

utils/gemini.py is the only module that talks to Gemini (no Streamlit imports). It builds one request per turn:

python
client.interactions.create(
    model="gemini-3.8-flash",
    input=user_text,
    system_instruction=...,
    previous_interaction_id=...,          # memory
    tools=[{"type": "google_search"}],    # Auto / Search modes only
)


Responses are a list of typed steps (thoughts, search calls, model_output). Nexa reads the final text, the interaction id and the grounding data through defensive helpers (utils/helpers.py), and never displays thought steps or raw JSON.

## 6. How Google Search grounding works

With the google_search tool enabled, the model decides whether to search, runs one or more queries, and returns text with inline url_citation annotations (URL, title, and the span of text each source supports).

- *Auto*: tool enabled, model decides.
- *Search*: tool enabled and the system instruction tells the model to research first.
- *Chat*: tool not sent.

utils/search.py extracts only what the API returned: queries from google_search_call steps, sources from url_citation annotations (deduplicated by URL), and the search-suggestions HTML Google returns. Google's grounding terms require showing search suggestions, so Nexa renders that widget under the sources. With Gemini 3 models, billing is per search query the model executes.

## 7. Architecture


Streamlit UI (app.py)
   │  user message, mode, style, model
   ▼
conversation.py ── session state: messages, interaction_id per conversation
   ▼
gemini.py ── interactions.create(previous_interaction_id, tools, system_instruction)
   ▼
search.py ── queries, sources, suggestions  →  stored with the message → UI


## 8. Project structure


Nexa/
├── app.py                 # Streamlit UI and turn handling
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   └── config.toml        # theme and client settings
└── utils/
    ├── __init__.py
    ├── gemini.py          # Gemini client, requests, error classification
    ├── conversation.py    # session-based conversation state
    ├── prompts.py         # system instruction, modes, styles, sample prompts
    ├── search.py          # grounding extraction and source formatting
    └── helpers.py         # safe response access, text/URL helpers, API key lookup


## 9. Technologies

Python 3.10+, Streamlit, google-genai (>= 2.3.0), the Gemini Interactions API and Grounding with Google Search.

## 10. Environment / API key

Nexa reads GEMINI_API_KEY from Streamlit secrets (falling back to an environment variable of the same name). The key is never hard-coded, logged or displayed. If it is missing, the app shows a setup message instead of failing.

Create a key in Google AI Studio: https://aistudio.google.com/apikey

## 11. Local installation

bash
git clone https://github.com/<your-username>/Nexa.git
cd Nexa
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt


Create .streamlit/secrets.toml (already git-ignored):

toml
GEMINI_API_KEY = "your-api-key"


## 12. Running the application

bash
streamlit run app.py


In GitHub Codespaces, run the same command and open the forwarded port. Alternatively, add GEMINI_API_KEY as a Codespaces secret.

## 13. Streamlit Community Cloud deployment

1. Push the project to a GitHub repository (confirm .streamlit/secrets.toml is not committed).
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Choose *Create app*, select the repository and branch, and set the main file path to app.py.
4. Open *Advanced settings → Secrets* and paste: GEMINI_API_KEY = "your-api-key".
5. Deploy. Later changes to the secret are made under *App settings → Secrets*.

## 14. Error handling

Failures are classified into friendly messages and logged server-side without secrets: missing or invalid key, quota/rate limit, network failure, unsupported model, lost conversation state, search failure, empty or malformed responses, and unexpected errors. Failed turns show a short note and a "Try again" button. Empty and over-long messages are rejected before any API call, and reruns never trigger duplicate requests.

## 15. Limitations

- Conversations live only in the browser session; refreshing the page loses them.
- Server-side context depends on Google's retention window (1 day free tier, 55 days paid).
- Responses are not streamed; the UI shows a spinner until the full answer arrives.
- Source snippets show which part of the answer each source supports, but citations are not inserted inline.
- Search availability and quotas depend on your Gemini API plan.
- The model list in utils/gemini.py may need updating as Google retires models.

## 16. Future improvements

- Streaming responses and live search status
- Inline numbered citations in the answer text
- Exporting a conversation as Markdown
- Optional persistent history with explicit user consent

## 17. QSkill requirement mapping

Adjust the wording below to match your official task description.

| Requirement | Where it is implemented |
|---|---|
| Gemini integration in Python | utils/gemini.py (google-genai, Interactions API) |
| Conversation history / memory | utils/conversation.py, previous_interaction_id in utils/gemini.py |
| Real-time information retrieval | Google Search grounding in utils/search.py and utils/gemini.py |
| Secure API key handling | utils/helpers.py (get_api_key), Streamlit secrets, .gitignore |
| Deployable web app | app.py, requirements.txt, Streamlit Community Cloud steps above |
