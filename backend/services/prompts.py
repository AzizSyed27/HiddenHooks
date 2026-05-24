"""
Prompt loader for Phase 5 multi-agent reasoning layer.

load_prompt(name) reads backend/prompts/<name>.md and caches at module level.
The cache persists for the process lifetime — prompts are git-tracked and do not
change at runtime. Restart the server to pick up prompt edits during development.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

_PROMPTS_DIR: Final = Path(__file__).parent.parent / "prompts"
_cache: dict[str, str] = {}


def load_prompt(name: str) -> str:
    """Return the text of backend/prompts/<name>.md, cached after first read.

    Args:
        name: Prompt file stem without extension, e.g. 'weather_agent'.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    if name not in _cache:
        _cache[name] = (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return _cache[name]
