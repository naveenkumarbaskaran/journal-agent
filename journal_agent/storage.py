"""
JournalStorage: saves and loads journal entries as dated Markdown files.

File naming convention: YYYY-MM-DD.md inside *journal_dir*.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path


class JournalStorage:
    """Manages a directory of dated Markdown journal files.

    Each entry is stored as ``<journal_dir>/YYYY-MM-DD.md``.
    """

    def __init__(self, journal_dir: str | os.PathLike[str] = "~/journal") -> None:
        self.journal_dir = Path(journal_dir).expanduser().resolve()
        self.journal_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def today_path(self, day: date | None = None) -> Path:
        """Return the Path for *day* (defaults to today)."""
        d = day or date.today()
        return self.journal_dir / f"{d.isoformat()}.md"

    # ------------------------------------------------------------------
    # Save / load
    # ------------------------------------------------------------------

    def save_entry(
        self,
        text: str,
        day: date | None = None,
        *,
        mood: str | None = None,
        themes: list[str] | None = None,
    ) -> Path:
        """Write *text* to the dated Markdown file, prepending YAML front-matter.

        Returns the path that was written.
        """
        path = self.today_path(day)
        front_matter = _build_front_matter(
            day=day or date.today(),
            mood=mood,
            themes=themes,
        )
        path.write_text(front_matter + text, encoding="utf-8")
        return path

    def load_entry(self, day: date | None = None) -> str | None:
        """Load and return the text for *day*, or ``None`` if it does not exist."""
        path = self.today_path(day)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_recent_entries(self, n_days: int = 7) -> list[Path]:
        """Return paths of entry files from the last *n_days* days, newest first.

        Only includes days that actually have a file.
        """
        today = date.today()
        paths: list[Path] = []
        for offset in range(n_days):
            candidate = self.today_path(today - timedelta(days=offset))
            if candidate.exists():
                paths.append(candidate)
        return paths

    def list_all_entries(self) -> list[Path]:
        """Return all ``*.md`` entry files in the journal directory, newest first."""
        files = sorted(
            self.journal_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"),
            reverse=True,
        )
        return files

    def entry_exists(self, day: date | None = None) -> bool:
        """Return True if an entry exists for *day* (defaults to today)."""
        return self.today_path(day).exists()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_front_matter(
    day: date,
    mood: str | None = None,
    themes: list[str] | None = None,
) -> str:
    """Return a YAML front-matter block for a journal entry."""
    lines = ["---"]
    lines.append(f"date: {day.isoformat()}")
    if mood:
        lines.append(f"mood: {mood}")
    if themes:
        # Render as a YAML sequence
        themes_yaml = ", ".join(f'"{t}"' for t in themes)
        lines.append(f"themes: [{themes_yaml}]")
    lines.append("---")
    lines.append("")  # blank line after front-matter
    return "\n".join(lines)
