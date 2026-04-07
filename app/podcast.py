import re

from .settings import get_setting

SYSTEM_PROMPT = """You are writing a script for a two-person podcast called "Deep Dive". The hosts are discussing content from a documentation wiki.

The two hosts are:
- Alex (HOST_A): The lead host — warm, curious, great at asking the right questions and making complex topics approachable. The listener's stand-in.
- Sam (HOST_B): The expert co-host — deeply knowledgeable, explains things clearly with good analogies, occasionally adds surprising insights.

Rules:
- Write natural, conversational dialogue — not a lecture or interview
- Both hosts should contribute substantively
- Include genuine reactions ("Oh interesting...", "Right, that makes sense", "Wait, so...")
- Cover all the important points from the source material
- Use accessible language — avoid jargon unless you explain it
- Start with a brief, energetic intro to hook the listener
- End with a concise wrap-up
- Aim for roughly 1500-2500 words of dialogue
- The hosts refer to each other by name (Alex and Sam), NEVER as "Host A" or "Host B"

Format each line exactly as:
HOST_A: [their words]
HOST_B: [their words]

The HOST_A/HOST_B labels are only for parsing — they must never appear in the spoken dialogue itself.
No stage directions, sound effects, or meta-commentary."""


async def generate_podcast_script(content: str, title: str) -> list[dict]:
    """Generate a conversational podcast script using the configured LLM."""
    provider = get_setting("llm_provider", "openai")
    if provider == "gemini":
        return await _generate_gemini(content, title)
    return await _generate_openai(content, title)


async def _generate_openai(content: str, title: str) -> list[dict]:
    from openai import AsyncOpenAI

    api_key = get_setting("openai_api_key")
    if not api_key:
        raise ValueError("OpenAI API key not configured — set it in Settings")

    client = AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=get_setting("llm_model", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Create a podcast episode discussing this content:\n\nTitle: {title}\n\n{content}",
            },
        ],
        max_tokens=4096,
        temperature=0.8,
    )

    script_text = response.choices[0].message.content
    segments = parse_script(script_text)
    if not segments:
        raise ValueError("Failed to generate podcast script")
    return segments


async def _generate_gemini(content: str, title: str) -> list[dict]:
    from google import genai

    api_key = get_setting("gemini_api_key")
    if not api_key:
        raise ValueError("Gemini API key not configured — set it in Settings")

    client = genai.Client(api_key=api_key)
    model = get_setting("llm_model", "gemini-2.5-flash")
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Create a podcast episode discussing this content:\n\n"
        f"Title: {title}\n\n{content}"
    )
    # Disable thinking — unnecessary for creative writing, saves ~30s
    from google.genai.types import GenerateContentConfig, ThinkingConfig
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=GenerateContentConfig(
            thinking_config=ThinkingConfig(thinking_budget=0),
            temperature=0.8,
        ),
    )

    segments = parse_script(response.text)
    if not segments:
        raise ValueError("Failed to generate podcast script")
    return segments


def parse_script(text: str) -> list[dict]:
    """Parse HOST_A/HOST_B formatted script into segments."""
    segments = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^HOST_([AB]):\s*(.+)$", line)
        if match:
            segments.append({"speaker": match.group(1), "text": match.group(2)})
    return segments
