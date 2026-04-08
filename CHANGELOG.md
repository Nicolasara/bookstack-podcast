# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-04-08

Initial public release.

### Features

- **Two conversion modes**: podcast (two-host LLM-generated discussion) and narration (single voice reading)
- **Multiple TTS engines**: Edge TTS (free) and OpenAI TTS (`gpt-4o-mini-tts`)
- **Multiple LLM providers**: OpenAI (gpt-4o-mini, gpt-4o, gpt-4.1-mini/nano) and Google Gemini (2.5-flash, 2.5-flash-lite, 3-flash-preview)
- **Podcast RSS feed** at `/feed.xml` for subscribing in any podcast app
- **Episode library** organized by BookStack shelf → book → page hierarchy
- **Multiple versions per page** (different voices, different modes)
- **Auto-convert** background worker that watches BookStack shelves and converts new pages on a schedule
- **Convert All** button for books and shelves to bulk-queue conversions
- **Search** by name, BookStack URL, or numeric ID
- **All settings in the UI** with auto-save (BookStack connection, API keys, voices, models, auto-convert)
- **Stale episode timeout** — episodes stuck >10 minutes auto-mark as errors
- **Parallel TTS generation** for podcast mode (dynamic TPM batching)
- **BookStack hack modules** (optional):
  - `bookstack-hack/`: Embedded audio player and convert buttons in BookStack page sidebar
  - `bookstack-hack-link/`: Lightweight Listen / Convert links

### Architecture

- FastAPI web service with Jinja2 templates
- SQLite for episode metadata and settings
- pydub + ffmpeg for audio segment concatenation
- Docker deployment with mounted data volume
