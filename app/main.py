import asyncio
import os
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .bookstack import BookStackClient
from .database import Database
from .feed import generate_podcast_feed
from .settings import get_setting, has_podcast_key, set_setting
from .tts import VOICE_OPTIONS, generate_audio, generate_podcast_audio

app = FastAPI(title="BookStack Podcast")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
AUDIO_DIR = DATA_DIR / "audio"

db = Database(DATA_DIR / "episodes.db")
bookstack = BookStackClient()
conversion_lock = asyncio.Lock()


@app.on_event("startup")
async def startup():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    await db.init()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    episodes = await db.get_episodes()
    has_pending = any(e["status"] in ("pending", "processing") for e in episodes)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "episodes": episodes,
            "voices": VOICE_OPTIONS,
            "has_pending": has_pending,
            "has_podcast": has_podcast_key(),
            "llm_provider": get_setting("llm_provider", "openai"),
            "has_openai_key": bool(get_setting("openai_api_key")),
            "has_gemini_key": bool(get_setting("gemini_api_key")),
        },
    )


@app.post("/convert")
async def convert(
    background_tasks: BackgroundTasks,
    bookstack_type: str = Form(...),
    bookstack_id: str = Form(...),
    voice: str = Form("en-US-AndrewMultilingualNeural"),
    mode: str = Form("narration"),
):
    resolved_id = await bookstack.resolve_query(bookstack_id, bookstack_type)
    existing = await db.get_episode_by_source(bookstack_type, resolved_id)

    if existing and existing["status"] in ("pending", "processing"):
        return RedirectResponse(url="/", status_code=303)

    if existing:
        # Re-convert: clean up old audio
        if existing["audio_filename"]:
            old_path = AUDIO_DIR / existing["audio_filename"]
            if old_path.exists():
                old_path.unlink()
        await db.update_episode(
            existing["id"], {"status": "pending", "error_message": None, "mode": mode}
        )
        episode_id = existing["id"]
    else:
        episode_id = await db.create_episode(bookstack_type, resolved_id)
        await db.update_episode(episode_id, {"mode": mode})

    background_tasks.add_task(
        process_conversion, episode_id, bookstack_type, resolved_id, voice, mode
    )
    return RedirectResponse(url="/", status_code=303)


async def process_conversion(
    episode_id: int,
    bookstack_type: str,
    bookstack_id: int,
    voice: str,
    mode: str,
):
    async with conversion_lock:
        try:
            await db.update_status(episode_id, "processing")

            if bookstack_type == "chapter":
                content = await bookstack.get_chapter(bookstack_id)
            else:
                content = await bookstack.get_page(bookstack_id)

            text = content["text"]
            if not text.strip():
                raise ValueError("Page has no text content")

            filename = f"{bookstack_type}_{bookstack_id}.mp3"
            output_path = AUDIO_DIR / filename

            if mode == "podcast":
                from .podcast import generate_podcast_script

                script = await generate_podcast_script(text, content["title"])
                duration = await generate_podcast_audio(script, str(output_path))
            else:
                duration = await generate_audio(text, str(output_path), voice)

            file_size = output_path.stat().st_size

            await db.update_episode(
                episode_id,
                {
                    "title": content["title"],
                    "description": content.get("description", ""),
                    "audio_filename": filename,
                    "duration_seconds": duration,
                    "file_size": file_size,
                    "voice": voice if mode == "narration" else "podcast",
                    "status": "done",
                    "error_message": None,
                    "mode": mode,
                },
            )
        except Exception as e:
            await db.update_status(episode_id, "error", str(e))


@app.post("/settings")
async def save_settings(
    llm_provider: str = Form("openai"),
    openai_api_key: str = Form(""),
    gemini_api_key: str = Form(""),
):
    set_setting("llm_provider", llm_provider)
    if openai_api_key:
        set_setting("openai_api_key", openai_api_key)
    if gemini_api_key:
        set_setting("gemini_api_key", gemini_api_key)
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/search")
async def search(q: str = ""):
    if not q.strip():
        return []
    return await bookstack.search(q)


@app.delete("/api/episodes/{episode_id}")
async def delete_episode(episode_id: int):
    episode = await db.get_episode(episode_id)
    if episode and episode["audio_filename"]:
        audio_path = AUDIO_DIR / episode["audio_filename"]
        if audio_path.exists():
            audio_path.unlink()
    await db.delete_episode(episode_id)
    return {"status": "deleted"}


@app.get("/feed.xml")
async def podcast_feed():
    episodes = await db.get_episodes(status="done")
    base_url = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
    xml = generate_podcast_feed(episodes, base_url)
    return Response(content=xml, media_type="application/rss+xml")


@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        return Response(status_code=400)
    path = AUDIO_DIR / filename
    if not path.exists():
        return Response(status_code=404)
    return FileResponse(path, media_type="audio/mpeg")
