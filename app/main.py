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

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="BookStack Podcast")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
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
    """Group episodes into shelf -> book -> page -> renderings structure."""
    shelves = OrderedDict()
    for ep in episodes:
        shelf = ep.get("shelf_name") or "Uncategorized"
        book = ep.get("book_name") or "Uncategorized"
        page_key = (ep["bookstack_type"], ep["bookstack_id"])

        if shelf not in shelves:
            shelves[shelf] = OrderedDict()
        if book not in shelves[shelf]:
            shelves[shelf][book] = OrderedDict()
        if page_key not in shelves[shelf][book]:
            shelves[shelf][book][page_key] = {
                "title": ep.get("title") or f"{ep['bookstack_type']} {ep['bookstack_id']}",
                "renderings": [],
            }
        shelves[shelf][book][page_key]["renderings"].append(ep)

    result = []
    for shelf_name, books in shelves.items():
        book_list = []
        for book_name, pages in books.items():
            book_list.append({
                "book_name": book_name,
                "pages": list(pages.values()),
            })
        result.append({
            "shelf_name": shelf_name,
            "books": book_list,
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
    asyncio.create_task(auto_convert_worker())


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, q: str = ""):
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
            "bookstack_url": get_setting("bookstack_url", ""),
            "has_bookstack_token": bool(get_setting("bookstack_token_id")),
            "auto_convert_enabled": get_setting("auto_convert_enabled", "false"),
            "auto_convert_shelves": get_setting("auto_convert_shelves", ""),
            "auto_convert_mode": get_setting("auto_convert_mode", "podcast"),
            "auto_convert_interval": get_setting("auto_convert_interval", "30"),
            "initial_query": q,
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
            "shelf_name": meta.get("shelf_name", ""),
            "shelf_id": meta.get("shelf_id"),
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
            "shelf_name": meta.get("shelf_name", ""),
            "shelf_id": meta.get("shelf_id"),
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
            "shelf_name": content.get("shelf_name", ""),
            "shelf_id": content.get("shelf_id"),
        })

        text = content["text"]
        if not text.strip():
            raise ValueError("Page has no text content")

        filename = _audio_filename(bookstack_type, bookstack_id, mode, voice)
        output_path = AUDIO_DIR / filename

        import time as _time

        if mode == "podcast":
            from .podcast import generate_podcast_script

            t0 = _time.monotonic()
            script = await generate_podcast_script(text, content["title"])
            t1 = _time.monotonic()
            duration = await generate_podcast_audio(script, str(output_path))
            t2 = _time.monotonic()
            import logging as _log; _log.warning(f"[ep {episode_id}] LLM script: {t1-t0:.1f}s ({len(script)} segments), TTS: {t2-t1:.1f}s, total: {t2-t0:.1f}s")
        else:
            t0 = _time.monotonic()
            duration = await generate_audio(text, str(output_path), voice)
            t1 = _time.monotonic()
            import logging as _log; _log.warning(f"[ep {episode_id}] TTS narration: {t1-t0:.1f}s")

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


async def auto_convert_worker():
    """Background worker that periodically scans watched shelves for new pages."""
    await asyncio.sleep(5)  # let app finish starting
    while True:
        try:
            if get_setting("auto_convert_enabled") == "true":
                await _scan_and_convert()
        except Exception:
            import traceback
            traceback.print_exc()
        interval = int(get_setting("auto_convert_interval", "30"))
        await asyncio.sleep(interval * 60)


async def _scan_and_convert():
    shelf_ids = get_setting("auto_convert_shelves", "")
    mode = get_setting("auto_convert_mode", "podcast")
    voice = get_setting("auto_convert_voice", "en-US-AndrewMultilingualNeural")
    effective_voice = "podcast" if mode == "podcast" else voice

    for shelf_id_str in shelf_ids.split(","):
        shelf_id_str = shelf_id_str.strip()
        if not shelf_id_str:
            continue
        pages = await bookstack.get_shelf_pages(int(shelf_id_str))
        for page in pages:
            existing = await db.get_episode_by_source(
                "page", page["id"], mode, effective_voice
            )
            if existing:
                continue
            # Create episode with metadata
            episode_id = await db.create_episode(
                "page", page["id"], mode, effective_voice
            )
            await db.update_episode(episode_id, {
                "title": page["name"],
                "book_name": page["book_name"],
                "book_id": page.get("book_id"),
                "shelf_name": page.get("shelf_name", ""),
                "shelf_id": page.get("shelf_id"),
            })
            await process_conversion(
                episode_id, "page", page["id"], voice, mode
            )


@app.post("/api/convert-all")
async def api_convert_all(
    background_tasks: BackgroundTasks,
    source_type: str = Form(...),
    source_id: str = Form(...),
    voice: str = Form("en-US-AndrewMultilingualNeural"),
    mode: str = Form("narration"),
):
    """Convert all pages in a book or shelf."""
    source_id_int = int(source_id)
    effective_voice = "podcast" if mode == "podcast" else voice

    if source_type == "bookshelf":
        pages = await bookstack.get_shelf_pages(source_id_int)
    elif source_type == "book":
        pages = await bookstack.get_book_pages(source_id_int)
    else:
        return {"status": "error", "message": f"Cannot convert all for type: {source_type}"}

    queued = 0
    for page in pages:
        existing = await db.get_episode_by_source(
            "page", page["id"], mode, effective_voice
        )
        if existing:
            continue
        episode_id = await db.create_episode(
            "page", page["id"], mode, effective_voice
        )
        await db.update_episode(episode_id, {
            "title": page["name"],
            "book_name": page["book_name"],
            "book_id": page.get("book_id"),
            "shelf_name": page.get("shelf_name", ""),
            "shelf_id": page.get("shelf_id"),
        })
        background_tasks.add_task(
            process_conversion, episode_id, "page", page["id"], voice, mode
        )
        queued += 1

    return {"status": "queued", "queued": queued, "total_pages": len(pages)}


@app.get("/api/page/{page_id}/episodes")
async def page_episodes(page_id: int):
    """Get all episodes for a specific page."""
    episodes = await db.get_episodes()
    results = []
    for e in episodes:
        if e["bookstack_type"] == "page" and e["bookstack_id"] == page_id:
            e["voice_label"] = _voice_label(e.get("voice", ""))
            results.append(e)
    return results


@app.get("/api/shelves")
async def list_shelves():
    return await bookstack.list_shelves()


@app.post("/settings")
async def save_settings(
    bookstack_url: str = Form(""),
    bookstack_token_id: str = Form(""),
    bookstack_token_secret: str = Form(""),
    tts_engine: str = Form("edge"),
    llm_provider: str = Form("openai"),
    openai_api_key: str = Form(""),
    gemini_api_key: str = Form(""),
    auto_convert_enabled: str = Form("false"),
    auto_convert_shelves: str = Form(""),
    auto_convert_mode: str = Form("podcast"),
    auto_convert_interval: str = Form("30"),
):
    if bookstack_url:
        set_setting("bookstack_url", bookstack_url)
    if bookstack_token_id:
        set_setting("bookstack_token_id", bookstack_token_id)
    if bookstack_token_secret:
        set_setting("bookstack_token_secret", bookstack_token_secret)
    set_setting("tts_engine", tts_engine)
    set_setting("llm_provider", llm_provider)
    if openai_api_key:
        set_setting("openai_api_key", openai_api_key)
    if gemini_api_key:
        set_setting("gemini_api_key", gemini_api_key)
    set_setting("auto_convert_enabled", auto_convert_enabled)
    set_setting("auto_convert_shelves", auto_convert_shelves)
    set_setting("auto_convert_mode", auto_convert_mode)
    set_setting("auto_convert_interval", auto_convert_interval)
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
