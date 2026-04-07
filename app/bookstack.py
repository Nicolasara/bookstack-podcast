import os
import re
from urllib.parse import urlparse

import httpx


BOOKSTACK_URL = os.environ.get("BOOKSTACK_URL", "http://192.168.6.177:8084")
BOOKSTACK_TOKEN_ID = os.environ.get("BOOKSTACK_TOKEN_ID", "")
BOOKSTACK_TOKEN_SECRET = os.environ.get("BOOKSTACK_TOKEN_SECRET", "")


class BookStackClient:
    def __init__(self):
        self.base_url = BOOKSTACK_URL.rstrip("/")
        self.headers = {
            "Authorization": f"Token {BOOKSTACK_TOKEN_ID}:{BOOKSTACK_TOKEN_SECRET}",
        }
        self._book_shelf_cache = {}

    async def _ensure_shelf_cache(self):
        """Build book_id -> shelf mapping by listing all shelves."""
        if self._book_shelf_cache:
            return
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/shelves", headers=self.headers
            )
            if resp.status_code != 200:
                return
            for shelf_summary in resp.json().get("data", []):
                shelf_resp = await client.get(
                    f"{self.base_url}/api/shelves/{shelf_summary['id']}",
                    headers=self.headers,
                )
                if shelf_resp.status_code != 200:
                    continue
                shelf = shelf_resp.json()
                for book in shelf.get("books", []):
                    self._book_shelf_cache[book["id"]] = {
                        "shelf_id": shelf_summary["id"],
                        "shelf_name": shelf_summary["name"],
                    }

    async def get_shelf_for_book(self, book_id: int) -> dict:
        await self._ensure_shelf_cache()
        return self._book_shelf_cache.get(
            book_id, {"shelf_id": None, "shelf_name": ""}
        )

    async def get_page(self, page_id: int) -> dict:
        async with httpx.AsyncClient() as client:
            meta_resp = await client.get(
                f"{self.base_url}/api/pages/{page_id}",
                headers=self.headers,
            )
            meta_resp.raise_for_status()
            meta = meta_resp.json()

            # Fetch book name
            book_name = ""
            if meta.get("book_id"):
                book_resp = await client.get(
                    f"{self.base_url}/api/books/{meta['book_id']}",
                    headers=self.headers,
                )
                if book_resp.status_code == 200:
                    book_name = book_resp.json().get("name", "")

            text_resp = await client.get(
                f"{self.base_url}/api/pages/{page_id}/export/plaintext",
                headers=self.headers,
            )
            text_resp.raise_for_status()

            text = clean_text_for_tts(text_resp.text, meta["name"])
            shelf_info = await self.get_shelf_for_book(meta.get("book_id")) if meta.get("book_id") else {"shelf_id": None, "shelf_name": ""}
            return {
                "title": meta["name"],
                "description": meta.get("description", ""),
                "text": text,
                "book_id": meta.get("book_id"),
                "book_name": book_name,
                "shelf_id": shelf_info["shelf_id"],
                "shelf_name": shelf_info["shelf_name"],
            }

    async def get_chapter(self, chapter_id: int) -> dict:
        async with httpx.AsyncClient() as client:
            meta_resp = await client.get(
                f"{self.base_url}/api/chapters/{chapter_id}",
                headers=self.headers,
            )
            meta_resp.raise_for_status()
            meta = meta_resp.json()

            # Fetch book name
            book_name = ""
            if meta.get("book_id"):
                book_resp = await client.get(
                    f"{self.base_url}/api/books/{meta['book_id']}",
                    headers=self.headers,
                )
                if book_resp.status_code == 200:
                    book_name = book_resp.json().get("name", "")

            text_resp = await client.get(
                f"{self.base_url}/api/chapters/{chapter_id}/export/plaintext",
                headers=self.headers,
            )
            text_resp.raise_for_status()

            text = clean_text_for_tts(text_resp.text, meta["name"])
            shelf_info = await self.get_shelf_for_book(meta.get("book_id")) if meta.get("book_id") else {"shelf_id": None, "shelf_name": ""}
            return {
                "title": meta["name"],
                "description": meta.get("description", ""),
                "text": text,
                "book_id": meta.get("book_id"),
                "book_name": book_name,
                "shelf_id": shelf_info["shelf_id"],
                "shelf_name": shelf_info["shelf_name"],
            }

    async def list_shelves(self) -> list:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/shelves",
                headers=self.headers,
            )
            resp.raise_for_status()
            return [{"id": s["id"], "name": s["name"]} for s in resp.json().get("data", [])]

    async def get_shelf_pages(self, shelf_id: int) -> list:
        """Get all pages across all books on a shelf."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/shelves/{shelf_id}",
                headers=self.headers,
            )
            resp.raise_for_status()
            shelf = resp.json()
            shelf_name = shelf.get("name", "")

            pages = []
            for book_info in shelf.get("books", []):
                book_resp = await client.get(
                    f"{self.base_url}/api/books/{book_info['id']}",
                    headers=self.headers,
                )
                if book_resp.status_code != 200:
                    continue
                book = book_resp.json()
                page_base = {
                    "book_name": book["name"],
                    "book_id": book["id"],
                    "shelf_name": shelf_name,
                    "shelf_id": shelf_id,
                }
                for item in book.get("contents", []):
                    if item["type"] == "page":
                        pages.append({"id": item["id"], "name": item["name"], **page_base})
                    elif item["type"] == "chapter":
                        ch_resp = await client.get(
                            f"{self.base_url}/api/chapters/{item['id']}",
                            headers=self.headers,
                        )
                        if ch_resp.status_code != 200:
                            continue
                        for page in ch_resp.json().get("pages", []):
                            pages.append({"id": page["id"], "name": page["name"], **page_base})
            return pages

    async def get_book_pages(self, book_id: int) -> list:
        """Get all pages in a book."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/api/books/{book_id}",
                headers=self.headers,
            )
            resp.raise_for_status()
            book = resp.json()
            shelf_info = await self.get_shelf_for_book(book_id)
            page_base = {
                "book_name": book["name"],
                "book_id": book_id,
                "shelf_name": shelf_info["shelf_name"],
                "shelf_id": shelf_info["shelf_id"],
            }

            pages = []
            for item in book.get("contents", []):
                if item["type"] == "page":
                    pages.append({"id": item["id"], "name": item["name"], **page_base})
                elif item["type"] == "chapter":
                    ch_resp = await client.get(
                        f"{self.base_url}/api/chapters/{item['id']}",
                        headers=self.headers,
                    )
                    if ch_resp.status_code != 200:
                        continue
                    for page in ch_resp.json().get("pages", []):
                        pages.append({"id": page["id"], "name": page["name"], **page_base
                        })
            return pages

    async def get_metadata(self, content_type: str, content_id: int) -> dict:
        """Lightweight fetch of just title and book name (no plaintext export)."""
        async with httpx.AsyncClient() as client:
            endpoint = "pages" if content_type == "page" else "chapters"
            resp = await client.get(
                f"{self.base_url}/api/{endpoint}/{content_id}",
                headers=self.headers,
            )
            resp.raise_for_status()
            meta = resp.json()

            book_name = ""
            if meta.get("book_id"):
                book_resp = await client.get(
                    f"{self.base_url}/api/books/{meta['book_id']}",
                    headers=self.headers,
                )
                if book_resp.status_code == 200:
                    book_name = book_resp.json().get("name", "")

            shelf_info = {"shelf_id": None, "shelf_name": ""}
            if meta.get("book_id"):
                shelf_info = await self.get_shelf_for_book(meta["book_id"])

            return {
                "title": meta["name"],
                "book_id": meta.get("book_id"),
                "book_name": book_name,
                "shelf_id": shelf_info["shelf_id"],
                "shelf_name": shelf_info["shelf_name"],
            }

    async def resolve_query(self, query: str, content_type: str) -> int:
        """Resolve a name, URL, or numeric ID to a BookStack page/chapter ID."""
        query = query.strip()

        # Direct numeric ID
        if query.isdigit():
            return int(query)

        # URL — extract slug from the last path segment
        search_term = query
        if "://" in query or query.startswith("/"):
            path_parts = [
                p for p in urlparse(query).path.split("/") if p
            ]
            if path_parts:
                search_term = path_parts[-1].replace("-", " ")

        results = await self.search(search_term)
        for r in results:
            if r["type"] == content_type:
                return r["id"]

        raise ValueError(f"No {content_type} found matching '{query}'")

    async def search(self, query: str) -> list:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/api/search",
                params={"query": query},
                headers=self.headers,
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for item in data.get("data", []):
                results.append(
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "type": item["type"],
                    }
                )
            return results


def clean_text_for_tts(text: str, title: str = "") -> str:
    """Clean up plaintext export for better TTS output."""
    # Remove URLs (they sound terrible spoken aloud)
    text = re.sub(r"https?://\S+", "", text)

    # Remove email addresses
    text = re.sub(r"\S+@\S+\.\S+", "", text)

    # Remove markdown-style header underlines
    text = re.sub(r"\n[=\-]{3,}\n", "\n\n", text)

    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    text = text.strip()

    if title:
        text = f"{title}.\n\n{text}"

    return text
