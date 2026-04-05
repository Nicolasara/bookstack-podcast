from datetime import datetime, timezone

from feedgen.feed import FeedGenerator


def generate_podcast_feed(episodes: list, base_url: str) -> str:
    fg = FeedGenerator()
    fg.load_extension("podcast")

    fg.title("BookStack Audio")
    fg.description("Audio versions of BookStack documentation pages")
    fg.link(href=base_url)
    fg.language("en")
    fg.podcast.itunes_category("Technology")
    fg.podcast.itunes_explicit("no")

    for ep in episodes:
        if ep["status"] != "done" or not ep.get("audio_filename"):
            continue

        fe = fg.add_entry()
        fe.id(f"{base_url}/audio/{ep['audio_filename']}")
        fe.title(ep["title"] or f"{ep['bookstack_type']} {ep['bookstack_id']}")
        fe.description(ep.get("description") or ep.get("title", ""))

        try:
            dt = datetime.fromisoformat(ep["created_at"]).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            dt = datetime.now(timezone.utc)
        fe.published(dt)

        fe.enclosure(
            url=f"{base_url}/audio/{ep['audio_filename']}",
            length=str(ep.get("file_size") or 0),
            type="audio/mpeg",
        )

        if ep.get("duration_seconds"):
            secs = int(ep["duration_seconds"])
            hours, remainder = divmod(secs, 3600)
            minutes, seconds = divmod(remainder, 60)
            fe.podcast.itunes_duration(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    return fg.rss_str(pretty=True).decode("utf-8")
