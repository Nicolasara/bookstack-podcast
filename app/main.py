import asyncio
import os
import re
from collections import OrderedDict
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .bookstack import BookStackClient
from .database import Database
from .feed import generate_podcast_feed
from .settings import get_setting, has_podcast_key, set_setting
from .tts import generate_audio, generate_podcast_audio, get_voice_options

app = FastAPI(title="BookStack Podcast")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
AUDIO_DIR = DATA_DIR / "audio"

db = Database(DATA_DIR / "episodes.db")
bookstack = BookStackClient()
conversion_lock = asyncio.Lock()


def _voice_label(voice_id: str) -> str:
    """Get short display name from a voice ID."""
    from .tts import VOICE_OPTIONS, OPENAI_VOICE_OPTIONS
    for vid, vname in VOICE_OPTIONS + OPENAI_VOICE_OPTIONS:
        if vid == voice_id:
            return vname
    return voice_id


def _group_episodes(episodes: list) -> list:
    """Group episodes into book -> page -> renderings structure."""
    books = OrderedDict()
    for ep in episodes:
        book = ep.get("book_name") or "Uncategorized"
        page_key = (ep["bookstack_type"], ep["bookstack_id"])
        if book not in books:
            books[book] = OrderedDict()
        if page_key not in books[book]:
            books[book][page_key] = {
                "title": ep.get("title") or f"{ep['bookstack_type']} {ep['bookstack_id']}",
                "renderings": [],
            }
        books[book][page_key]["renderings"].append(ep)

    result = []
    for book_name, pages in books.items():
        result.append({
            "book_name": book_name,
            "pages": list(pages.values()),
        })
    return result


def _audio_filename(bookstack_type: str, bookstack_id: int, mode: str, voice: str) -> str:
    """Generate a unique filename for an episode."""
    if mode == "podcast":
        return f"{bookstack_type}_{bookstack_id}_podcast.mp3"
    # Extract short name: en-US-AndrewMultilingualNeural -> andrew
    short = re.sub(r"(Multilingual)?Neural$", "", voice.split("-")[-1]).lower()
    return f"{bookstack_type}_{bookstack_id}_{short}.mp3"


@app.on_event("startup")
async def startup():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    await db.init()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    episodes = await db.get_episodes()
    has_pending = any(e["status"] in ("pending", "processing") for e in episodes)
    for ep in episodes:
        ep["voice_label"] = _voice_label(ep.get("voice", ""))
    grouped = _group_episodes(episodes)
    tts_engine = get_setting("tts_engine", "edge")
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "episodes": episodes,
            "grouped": grouped,
            "voices": get_voice_options(),
            "tts_engine": tts_engine,
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
    effective_voice = "podcast" if mode == "podcast" else voice

    existing = await db.get_episode_by_source(
        bookstack_type, resolved_id, mode, effective_voice
    )

    if existing and existing["status"] in ("pending", "processing"):
        return RedirectResponse(url="/", status_code=303)

    # Fetch metadata now so the UI shows title/book immediately
    meta = await bookstack.get_metadata(bookstack_type, resolved_id)

    if existing:
        # Re-convert same version: clean up old audio
        if existing["audio_filename"]:
            old_path = AUDIO_DIR / existing["audio_filename"]
            if old_path.exists():
                old_path.unlink()
        await db.update_episode(existing["id"], {
            "status": "pending",
            "error_message": None,
            "title": meta["title"],
            "book_name": meta["book_name"],
            "book_id": meta.get("book_id"),
        })
        episode_id = existing["id"]
    else:
        episode_id = await db.create_episode(
            bookstack_type, resolved_id, mode, effective_voice
        )
        await db.update_episode(episode_id, {
            "title": meta["title"],
            "book_name": meta["book_name"],
            "book_id": meta.get("book_id"),
        })

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

            # Save metadata immediately so the UI shows title while processing
            await db.update_episode(episode_id, {
                "title": content["title"],
                "description": content.get("description", ""),
                "book_id": content.get("book_id"),
                "book_name": content.get("book_name", ""),
            })

            text = content["text"]
            if not text.strip():
                raise ValueError("Page has no text content")

            filename = _audio_filename(bookstack_type, bookstack_id, mode, voice)
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
                    "book_id": content.get("book_id"),
                    "book_name": content.get("book_name", ""),
                    "status": "done",
                    "error_message": None,
                },
            )
        except Exception as e:
            await db.update_status(episode_id, "error", str(e))


@app.post("/settings")
async def save_settings(
    tts_engine: str = Form("edge"),
    llm_provider: str = Form("openai"),
    openai_api_key: str = Form(""),
    gemini_api_key: str = Form(""),
):
    set_setting("tts_engine", tts_engine)
    set_setting("llm_provider", llm_provider)
    if openai_api_key:
        set_setting("openai_api_key", openai_api_key)
    if gemini_api_key:
        set_setting("gemini_api_key", gemini_api_key)
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/search")
async def search(q: str = ""):
    q = q.strip()
    if not q:
        return []
    # If input looks like a URL, extract the slug for search
    if "://" in q or q.startswith("/"):
        from urllib.parse import urlparse

        path_parts = [p for p in urlparse(q).path.split("/") if p]
        if path_parts:
            q = path_parts[-1].replace("-", " ")
    return await bookstack.search(q)


@app.get("/api/episodes/status")
async def episodes_status():
    """Lightweight endpoint for polling episode status changes."""
    episodes = await db.get_episodes()
    return [
        {"id": e["id"], "status": e["status"], "title": e["title"]}
        for e in episodes
    ]


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
