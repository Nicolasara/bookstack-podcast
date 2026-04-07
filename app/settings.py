import json
import os
from pathlib import Path

SETTINGS_FILE = Path(os.environ.get("DATA_DIR", "/app/data")) / "settings.json"


def get_setting(key: str, default=None):
    """Read a setting, checking the file first then falling back to env vars."""
    # File settings take priority
    if SETTINGS_FILE.exists():
        data = json.loads(SETTINGS_FILE.read_text())
        val = data.get(key)
        if val:
            return val
    # Fall back to env vars for backwards compat
    env_map = {
        "openai_api_key": "OPENAI_API_KEY",
        "gemini_api_key": "GEMINI_API_KEY",
        "llm_provider": "LLM_PROVIDER",
        "bookstack_url": "BOOKSTACK_URL",
        "bookstack_token_id": "BOOKSTACK_TOKEN_ID",
        "bookstack_token_secret": "BOOKSTACK_TOKEN_SECRET",
    }
    if key in env_map:
        val = os.environ.get(env_map[key])
        if val:
            return val
    return default


def set_setting(key: str, value: str):
    data = {}
    if SETTINGS_FILE.exists():
        data = json.loads(SETTINGS_FILE.read_text())
    data[key] = value
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))


def has_podcast_key() -> bool:
    """Check if any LLM API key is configured for podcast mode."""
    provider = get_setting("llm_provider", "openai")
    if provider == "gemini":
        return bool(get_setting("gemini_api_key"))
    return bool(get_setting("openai_api_key"))
