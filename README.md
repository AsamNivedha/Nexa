# Nexa — AI That Understands Context

Nexa is a context-aware AI research assistant built with Python, Streamlit, and Google's Gemini API. It maintains conversational context across follow-up questions and uses Google Search grounding to research current information and display its sources.

## Features

- **Context-aware conversations:** Maintains conversation context using the Gemini Interactions API.
- **Three interaction modes:**
  - **Auto:** Allows Gemini to decide when web research is useful.
  - **Search:** Encourages research before answering.
  - **Chat:** Answers without enabling Google Search grounding.
- **Grounded research:** Extracts search queries, source citations, and search suggestions returned by Gemini.
- **Source transparency:** Displays research sources and explains when current information was used.
- **Conversation management:** Supports multiple conversations, starting a new conversation, and clearing the current conversation.
- **Response customization:** Choose Concise, Balanced, or Detailed responses and select an available Gemini model.
- **Error handling:** Provides user-friendly error messages and retry functionality without exposing raw tracebacks.
- **Secure configuration:** Reads the Gemini API key from Streamlit secrets or an environment variable.

## How It Works

Nexa combines conversational memory, language-model reasoning, and web-grounded research.

1. The user submits a message through the Streamlit interface.
2. The conversation manager retrieves the current conversation's state.
3. The Gemini client sends the message, system instructions, selected model, and applicable tools to the Interactions API.
4. When Google Search grounding is enabled, Gemini can execute searches and return grounded responses with source annotations.
5. Nexa extracts the response text, interaction identifier, search queries, and source information.
6. The interface displays the answer and its associated research information.

### Conversation Memory

Nexa stores the latest Gemini interaction ID for each conversation in Streamlit session state. Subsequent requests use `previous_interaction_id` to continue the conversation without manually resending the entire message history.

Each conversation maintains its own interaction ID, allowing users to switch between conversations without mixing their contexts.

**Important:** Conversation continuity depends on the availability of the stored Gemini interaction. Clearing local session state does not automatically guarantee that all remotely stored interaction data has been deleted.

### Google Search Grounding

Nexa uses Gemini's Google Search tool when research is enabled.

- **Auto:** Search is available when Gemini determines it is useful.
- **Search:** The system instructions encourage research before answering.
- **Chat:** Google Search is not included in the request.

The application extracts source URLs and titles from returned citation annotations and deduplicates sources by URL. It also displays search queries and Google-provided search suggestions when available.

Source availability and grounding behavior depend on the API response, selected model, and applicable Google API restrictions.

## Architecture

```text
                 Streamlit UI
                    app.py
                      |
                      v
              Conversation Manager
             utils/conversation.py
                      |
                      v
                Gemini Client
                utils/gemini.py
                      |
                      v
           Gemini Interactions API
                      |
             +--------+--------+
             |                 |
             v                 v
        Model Response     Google Search
             |              Grounding
             +--------+--------+
                      |
                      v
             Response Processing
              utils/helpers.py
              utils/search.py
                      |
                      v
             Answer + Sources
                      |
                      v
                 Streamlit UI
```

## Project Structure

```text
Nexa/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   └── config.toml
└── utils/
    ├── __init__.py
    ├── gemini.py
    ├── conversation.py
    ├── prompts.py
    ├── search.py
    └── helpers.py
```

| File | Responsibility |
|---|---|
| `app.py` | Streamlit interface, user input, response display, and interaction handling |
| `utils/gemini.py` | Gemini client, API requests, model configuration, and error classification |
| `utils/conversation.py` | Conversation state and session management |
| `utils/prompts.py` | System instructions, interaction modes, response styles, and example prompts |
| `utils/search.py` | Search-query extraction, citation processing, and source formatting |
| `utils/helpers.py` | Safe response access, text and URL utilities, and API key retrieval |
| `requirements.txt` | Python dependencies |
| `.streamlit/config.toml` | Streamlit configuration and theme settings |

## Technology Stack

- **Language:** Python 3.10+
- **Frontend:** Streamlit
- **AI integration:** Google Gemini API
- **SDK:** `google-genai`
- **Conversation continuity:** Gemini Interactions API
- **Web research:** Grounding with Google Search

## Prerequisites

Before running Nexa, install:

- Python 3.10 or later
- Git
- A Google AI Studio API key
- The Python dependencies listed in `requirements.txt`

Create an API key through [Google AI Studio](https://aistudio.google.com/apikey).

## Installation

### 1. Clone the repository

Replace `<your-username>` with your GitHub username.

```bash
git clone https://github.com/<your-username>/Nexa.git
cd Nexa
```

### 2. Create and activate a virtual environment

**Windows — PowerShell**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Windows — Command Prompt**

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

**Linux, macOS, or GitHub Codespaces**

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure the API key

Create `.streamlit/secrets.toml` in the project root:

```toml
GEMINI_API_KEY = "your-api-key"
```

Alternatively, set the `GEMINI_API_KEY` environment variable.

**Security:** Never commit API keys or the `.streamlit/secrets.toml` file. Ensure that the file is covered by `.gitignore` before pushing changes to GitHub.

### 5. Run Nexa

```bash
streamlit run app.py
```

Streamlit will display the local URL for the application, usually `http://localhost:8501`.

## Deployment

Nexa can be deployed using Streamlit Community Cloud.

1. Push the project to a GitHub repository.
2. Open [Streamlit Community Cloud](https://share.streamlit.io/).
3. Create a new app and select the repository and branch.
4. Set the main file path to `app.py`.
5. Open the app's advanced settings and locate the secrets configuration.
6. Add the following configuration:

   ```toml
   GEMINI_API_KEY = "your-api-key"
   ```

7. Deploy the application.

For GitHub Codespaces, configure `GEMINI_API_KEY` as a Codespaces secret, expose it to the running environment, and start the application using `streamlit run app.py`.

Never include API keys in source code, README examples containing real credentials, or committed configuration files.

## Error Handling

Nexa is designed to handle common failures, including:

- Missing or invalid API keys
- API quota and rate-limit errors
- Network failures
- Unsupported or unavailable models
- Expired or unavailable conversation context
- Search and grounding failures
- Empty or malformed API responses
- Unexpected application errors

The application should display actionable, user-friendly messages while keeping sensitive information and raw tracebacks out of the interface. Failed requests can be retried where supported.

Input validation should reject empty or excessively long messages before making API calls. Streamlit reruns should also be handled carefully to avoid accidental duplicate requests.

## Limitations

- **Session-based history:** Conversations are held in Streamlit session state and may be lost when the browser session resets or the application session is recreated.
- **Server-side context retention:** Continuing an old conversation depends on the availability of the stored Gemini interaction.
- **Non-streaming responses:** Answers are displayed after the request completes rather than progressively as tokens arrive.
- **Source presentation:** Sources are displayed separately from the answer; inline numbered citations are not currently part of the described interface.
- **API dependency:** Search availability, model access, quotas, and costs depend on Google's API policies and account configuration.
- **Model maintenance:** The configured model list must be updated as models become unavailable or are replaced.

## Future Improvements

- Stream responses as they are generated.
- Add inline citations linked to individual claims.
- Show live research status and search progress.
- Export conversations to Markdown.
- Add optional persistent conversation history with explicit user consent.
- Add automated tests for conversation management, citation extraction, error handling, and API response parsing.

## QSkill Requirement Mapping

Update this section to match the official internship task description and verify that each listed feature exists in the implementation.

| Requirement | Implementation |
|---|---|
| Gemini integration using Python | `utils/gemini.py` |
| Conversation memory | `utils/conversation.py` and interaction IDs in `utils/gemini.py` |
| Current-information retrieval | Google Search grounding in `utils/gemini.py` and `utils/search.py` |
| API key security | `utils/helpers.py`, Streamlit secrets, and `.gitignore` |
| Deployable web application | `app.py`, `requirements.txt`, and Streamlit Community Cloud configuration |

## Contributing

1. Fork the repository.
2. Create a branch for your changes.
3. Implement and test your changes.
4. Open a pull request describing the changes and validation performed.

## License

No license has been specified. Add a `LICENSE` file before presenting the project as open source, and choose a license appropriate for your intended use.

---

**Nexa — AI that understands context.**
