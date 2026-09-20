# LLM Personal Assistant

Modular personal-assistant API in Docker:

- **Local inference** — runs [Qwen3-0.6B-heretic-abliterated-uncensored-i1-GGUF](https://huggingface.co/mradermacher/Qwen3-0.6B-heretic-abliterated-uncensored-i1-GGUF) (Q4_K_M by default) via `llama-cpp-python` with native Qwen3 function/tool calling.
- **Pattern → tool short-circuit** — `/assistant` routes messages through a regex router; on a match the tool runs directly without touching the LLM, otherwise it falls back to the local model with tool calling.
- **Heavy reasoning via OpenRouter** — `/reasoning` sends reasoning/agentic jobs to OpenRouter's free router (`openrouter/free`) or any free model you specify (`model: "...:free"`).
- **Telegram bot (Node.js)** — pattern-driven message handling. A YouTube URL triggers "Baixando...." messages and then calls your `/mp3` endpoint (default `http://localhost:3021/mp3`); every other message is forwarded to the local assistant.

## Routes

| Route | Behaviour |
| --- | --- |
| `POST /chat` | Straight local Qwen3 chat. The model gets the tools schema and may emit tool calls (reported in the response; they are not executed). |
| `POST /assistant` | Pattern router. `handled_by: "tool"` when a rule matches (direct tool execution, zero LLM latency), otherwise `handled_by: "llm"` with the local model executing tool calls in a loop. |
| `POST /reasoning` | OpenRouter (free models by default). Non-streaming JSON or `stream: true` SSE. |
| `GET /models` | Lists currently-free OpenRouter model IDs (needs API key). |
| `GET /health` | Model download/load status + configured capabilities. |
| Telegram bot | Polls Telegram. YouTube URL → downloads MP3 via your endpoint and sends it with "Baixando...." messages in between; anything else → forwarded to `POST /assistant`. |

## Telegram bot

A Node.js bot in `./bot`. Get a token from [@BotFather](https://t.me/BotFather). Flow when a message matches a route:

1. Bot replies with the first `intermediary_messages` entry (e.g. "Baixando....").
2. Bot calls the route's `endpoint` (the YouTube URL is passed via the `{url}` placeholder or `?param=...`).
3. Bot sends the remaining intermediary messages with a small delay between them.
4. Bot sends the returned `.mp3` to the chat as audio.

Routes are declarative — one object in `BOT_ROUTES` per pattern:

```json
{
  "name": "youtube_mp3",
  "pattern": "https?://(www\\.)?youtube\\.com/watch\\?v=",
  "intermediary_messages": ["Baixando....", "Convertendo para MP3...", "Quase la..."],
  "endpoint": "http://localhost:3021/mp3",
  "method": "GET",
  "param": "url",
  "filename": "audio.mp3",
  "audio_title": "YouTube Audio",
  "error_message": "Nao consegui baixar esse video."
}
```

Optional route fields: `name`, `filename`, `audio_title`, `audio_performer`, `caption`, `error_message`. `endpoint` can contain `{url}` (replaced with the encoded URL) or use `param` (appended as a query key).

The downloader service (e.g. the `/mp3` endpoint) often runs on the host while the bot runs in Docker; in that case point the endpoint at `http://host.docker.internal:3021/mp3` (the bot service already maps `host.docker.internal` to the host gateway). Non-matching messages hit `BOT_ASSISTANT_ENDPOINT` (`http://assistant:8000/assistant` inside compose; `http://localhost:8000/assistant` when running the bot locally).

## Quick start

```powershell
Copy-Item .env.example .env
# edit .env: set OPENROUTER_API_KEY=sk-or-... and BOT_TOKEN (from @BotFather)
docker compose up --build
```

First container start downloads the ~380 MB GGUF into `./models` (kept on a volume), so subsequent starts are instant.

Smoke test on Windows:

```powershell
.\scripts\smoke.ps1
```

or via curl:

```bash
curl -s http://localhost:8000/health

# direct tool call (no LLM)
curl -s -X POST http://localhost:8000/assistant -H "Content-Type: application/json" \
  -d '{"message": "roll 2d6"}'

# LLM with tool calling
curl -s -X POST http://localhost:8000/assistant -H "Content-Type: application/json" \
  -d '{"message": "what time is it really? use the tool"}'

# heavy reasoning on a free OpenRouter model
curl -s -X POST http://localhost:8000/reasoning -H "Content-Type: application/json" \
  -d '{"message": "Walk through the proof that the square root of 2 is irrational.", "model": "openrouter/free"}'
```

## How the pattern router works

Matching is case-insensitive, anchored to the start of the message. Rules live in `backend/app/pattern.py` (`DEFAULT_RULES`); override them with the `TOOL_ROUTING_RULES` env var (JSON `{"rules": [...]}`).

| Pattern example | Tool | Args |
| --- | --- | --- |
| `what time is it` | `get_current_time` | — |
| `what's the date` | `get_current_date` | — |
| `calc (12+34)*5` | `calculate` | `expression` (regex group) |
| `roll 3 d8` | `roll_dice` | `count`, `sides` |
| `weather in Lisbon` | `get_weather` (wttr.in) | `city` |
| `search fastapi docs` | `web_search` (DuckDuckGo) | `query` |

Custom rule entry:

```json
{
  "name": "direct:uppercase",
  "pattern": "^(?:shout) (?P<text>.+)$",
  "tool": "web_search",
  "args": {"query": "x"},
  "args_from_groups": ["text"]
}
```

## Tools

Tools live in `backend/app/tools/builtin.py`. Each is a plain typed Python function; the JSON schema sent to the model is generated from its signature + docstring. Register any new function by adding it to `BUILTIN_TOOLS` — it appears in `/assistant/tools` and becomes available to both the local model and the pattern router.

## Environment variables

See `.env.example`. Relevant ones:

- `MODEL_FILENAME` — pick a different quant (e.g. `...i1-Q4_0.gguf`) from the same repo.
- `LLAMA_N_GPU_LAYERS` — set `99` for GPU offload (CPU by default). For real CUDA wheels, build with `docker build --build-arg CUDA=1 ./backend`.
- `LLAMA_CHAT_FORMAT` — leave empty (auto-detects Qwen3 jinja from the GGUF). If tool calls misparse, set to `qwen3`.
- `OPENROUTER_MODEL` — default `openrouter/free` (auto free router). Set e.g. `nvidia/nemotron-3-ultra-550b-a55b:free` for a fixed free reasoning model. The free catalog changes often; refresh with `GET /models`.
- `MAX_TOOL_ITERATIONS` — cap on the local tool-call loop.

## Notes

- The local 0.6B model is fast but weak at executing tools; the pattern router gives the deterministic, low-latency path while `/reasoning` gives quality on demand.
- The local engine serializes requests under a lock (single GGUF instance).