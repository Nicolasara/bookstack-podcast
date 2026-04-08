# BookStack Podcast

Convert [BookStack](https://www.bookstackapp.com/) wiki pages into audio you can listen to — either as a **two-host podcast discussion** or a **single-voice narration**.

## Features

- **Podcast mode** — An LLM generates a conversational script between two hosts, rendered with two alternating TTS voices
- **Narration mode** — A single TTS voice reads the page content directly
- **Podcast RSS feed** — Subscribe in any podcast app (Pocket Casts, AntennaPod, etc.)
- **Multiple TTS engines** — Edge TTS (free) or OpenAI TTS (fast)
- **Multiple LLM providers** — OpenAI or Google Gemini for podcast script generation
- **Multiple versions per page** — Same page can have podcast + narration with different voices
- **Auto-convert** — Watch BookStack shelves and automatically convert new pages on a schedule
- **BookStack hack** — Optional module that embeds an audio player and convert button directly into BookStack pages
- **Episode library** — Organized by BookStack shelf / book / page hierarchy
- **All settings in the UI** — BookStack connection, API keys, voices, models, auto-convert — no config files needed after initial deploy

## Quick Start

### 1. Create a BookStack API token

In BookStack, go to your profile > **API Tokens** > **Create Token**.

### 2. Run the container

The easiest way is to use the pre-built image from GitHub Container Registry:

```bash
docker run -d \
  --name bookstack-podcast \
  -p 8300:8000 \
  -v ./data:/app/data \
  --restart unless-stopped \
  ghcr.io/nicolasara/bookstack-podcast:latest
```

Or with Docker Compose:

```yaml
services:
  bookstack-podcast:
    image: ghcr.io/nicolasara/bookstack-podcast:latest
    container_name: bookstack-podcast
    ports:
      - "8300:8000"
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

### 3. Configure

Open `http://localhost:8300` and click **Settings**. Configure:

- **BookStack Connection** — your BookStack URL and API token
- **Text-to-Speech** — pick an engine (Edge TTS works without any API key)
- **Podcast Script (LLM)** — only needed for podcast mode, requires an OpenAI or Gemini API key

That's it. All settings auto-save. Search for a page and convert it.

### Building from source

If you want to build the image yourself:

```bash
git clone https://github.com/Nicolasara/bookstack-podcast.git
cd bookstack-podcast
docker compose up -d --build
```

### 3. (Optional) API keys

- **Without any API keys**: Edge TTS narration works out of the box (free, no key needed)
- **For podcast mode**: Add an OpenAI or Google Gemini API key in Settings
- **For faster TTS**: Add an OpenAI API key and switch to OpenAI TTS in Settings

## Configuration

All settings can be configured in the web UI under **Settings**. Environment variables work as fallbacks for initial setup or Docker-based configuration.

| Setting | Env Variable | Default | Description |
|---|---|---|---|
| BookStack URL | `BOOKSTACK_URL` | — | Your BookStack instance URL |
| BookStack Token ID | `BOOKSTACK_TOKEN_ID` | — | API token ID |
| BookStack Token Secret | `BOOKSTACK_TOKEN_SECRET` | — | API token secret |
| Service URL | `BASE_URL` | `http://localhost:8300` | Public URL (used in RSS feed links) |
| TTS Engine | `TTS_ENGINE` | `edge` | `edge` or `openai` |
| LLM Provider | `LLM_PROVIDER` | `openai` | `openai` or `gemini` |
| OpenAI API Key | `OPENAI_API_KEY` | — | Used for TTS and/or LLM |
| Gemini API Key | `GEMINI_API_KEY` | — | Used for LLM |

## TTS Engines

| Engine | Quality | Speed | Cost |
|---|---|---|---|
| **Edge TTS** | Very natural | Moderate (sequential for podcast) | Free |
| **OpenAI TTS** | Excellent | Fast (parallel segment generation) | ~$0.015/1K chars |

OpenAI TTS uses `gpt-4o-mini-tts-2025-03-20` with batched parallel requests for podcast mode.

## LLM Providers (Podcast Mode)

| Provider | Speed | Cost |
|---|---|---|
| **OpenAI** (gpt-4o-mini) | ~3s | ~$0.01/episode |
| **Google Gemini** (2.5-flash) | ~15s | Free tier available |

## BookStack Hack (Optional)

A companion BookStack theme module embeds an audio player and convert buttons directly into BookStack page sidebars, so you don't need to leave BookStack to listen to or generate podcasts.

It's a separate project: **[bookstack-podcast-hack](https://github.com/Nicolasara/bookstack-podcast-hack)**.

## API

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Web UI |
| `/feed.xml` | GET | Podcast RSS feed |
| `/audio/{filename}` | GET | Serve audio files |
| `/convert` | POST | Queue a conversion (form POST, redirects) |
| `/api/convert` | POST | Queue a conversion (JSON response) |
| `/api/convert-all` | POST | Convert all pages in a book or shelf |
| `/api/search?q=` | GET | Search BookStack content |
| `/api/page/{id}/episodes` | GET | Get episodes for a page |
| `/api/episodes/status` | GET | Poll episode statuses |
| `/api/shelves` | GET | List BookStack shelves |
| `/settings` | POST | Save settings |

## Architecture

```
BookStack ──API──> bookstack-podcast ──> LLM (script) ──> TTS (audio)
                         │
                         ├── SQLite (episodes, settings)
                         ├── /data/audio/ (MP3 files)
                         └── /feed.xml (podcast RSS)
```

- **FastAPI** web service with Jinja2 templates
- **SQLite** for episode metadata and settings
- **edge-tts** or **OpenAI TTS** for audio generation
- **OpenAI** or **Google Gemini** for podcast script generation
- **pydub + ffmpeg** for audio segment concatenation
- **Docker** deployment with a mounted data volume

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
DATA_DIR=./data uvicorn app.main:app --reload --port 8300

# Build Docker image
docker compose build
```

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. All commits must include a Developer Certificate of Origin sign-off (`git commit -s`).
