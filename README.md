# Lyftr AI

Lyftr AI is a local chat application with a React/Vite frontend and a FastAPI backend. The backend routes requests through LiteLLM, supports ordered OpenAI/Gemini fallback, stores chat history in SQLite, and can cache responses in memory.

## Features

- Chat interface with optional per-session system prompt
- OpenAI as the primary provider and Gemini as a fallback (provider order follows `LLM_API_KEYS`)
- SQLite persistence for sessions and messages
- Optional in-memory response cache
- Concise, complete responses by default, with basic Markdown rendering in the chat UI
- Health and session-history endpoints

## Requirements

- Python 3.13
- Node.js 22 and npm
- Docker Desktop, if using the Docker setup
- An OpenAI API key, a Gemini API key, or both

## Configure API keys

Create `.env` from `.env.example` if it does not already exist:

```powershell
Copy-Item .env.example .env
```

Edit `LLM_API_KEYS` in `.env`. Name each value for its provider, and put the preferred provider first:

```dotenv
LLM_API_KEYS=openai=sk-proj-your-openai-key,gemini=your-gemini-key
```

Do not commit `.env` or share its contents. The `openai` and `gemini` labels select the correct provider. Gemini is also recognized from a Google AI Studio key prefix. When both providers are configured, the backend tries them in the order listed.

Other settings:

| Setting | Default | Purpose |
| --- | --- | --- |
| `LLM_MODEL` | `gpt-4o-mini` | OpenAI model ID |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model ID; omit the `gemini/` provider prefix |
| `LLM_MAX_OUTPUT_TOKENS` | `2048` | Maximum response tokens, not a target length |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLite database location |
| `CACHE_ENABLED` | `true` | Enables the in-memory response cache |
| `ENABLE_FAILURE_SIMULATION` | `false` | Enables the optional provider-failure simulation header |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Backend target for the local Vite proxy |

## Run locally on Windows

From the repository root, create the backend environment and install dependencies:

```powershell
py -3.13 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Open two VS Code terminals.

**Terminal 1 — backend:**

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file ..\.env
```

**Terminal 2 — frontend:**

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

Open the local URL Vite prints, usually [http://127.0.0.1:5173](http://127.0.0.1:5173). The backend API is on port `8000`; it is not the chat page. If Vite reports that port `5173` is busy, use the alternate URL it prints or stop the other process using that port.

Backend health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)  
Interactive API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Run with Docker Compose

Make sure `.env` is configured, then run from the repository root:

```powershell
docker compose up --build -d
```

Open [http://localhost:3000](http://localhost:3000). The backend is available at [http://localhost:8000](http://localhost:8000).

View logs and stop the services:

```powershell
docker compose logs -f
docker compose down
```

The SQLite database is stored in the `lyftr_data` Docker volume and remains when containers are stopped with `docker compose down`.

## API

### `GET /health`

Returns service status, the number of configured provider keys, and whether caching is enabled.

### `POST /chat`

Request body:

```json
{
  "session_id": "a-unique-session-id",
  "message": "Explain Docker in a few sentences.",
  "system_prompt": "Optional instructions for this session."
}
```

`system_prompt` is optional. The backend adds concise-response guidance by default, while allowing the assistant to expand when asked. Responses include the reply and metadata such as model, latency, token counts, selected key ID, and whether the result came from the cache.

### `GET /sessions/{session_id}/messages`

Returns the saved conversation for a session. Returns `404` when the session does not exist.

## Project layout

```text
backend/       FastAPI app, LiteLLM routing, SQLite storage
frontend/      React app and Vite development server
.env.example   Environment-variable template
docker-compose.yml
```
