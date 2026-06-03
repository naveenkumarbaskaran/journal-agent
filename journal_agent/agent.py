"""
JournalAgent: Uses the Anthropic SDK to drive personalized daily prompts,
mood/theme tagging, and weekly reflections via an agentic tool-use loop.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import anthropic

from .storage import JournalStorage

MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Tool implementations (plain Python — called by the agentic loop)
# ---------------------------------------------------------------------------

def _read_file(path: str) -> str:
    """Return the contents of *path*, or an error string if not found."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"[file not found: {path}]"
    except Exception as exc:  # noqa: BLE001
        return f"[error reading {path}: {exc}]"


def _write_file(path: str, content: str) -> str:
    """Write *content* to *path*, creating parent directories as needed."""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} bytes to {path}"
    except Exception as exc:  # noqa: BLE001
        return f"[error writing {path}: {exc}]"


def _get_past_entries(journal_dir: str, n_days: int) -> str:
    """Return the last *n_days* journal entries as concatenated Markdown text."""
    storage = JournalStorage(journal_dir)
    entries = storage.list_recent_entries(n_days)
    if not entries:
        return "[no past entries found]"
    parts: list[str] = []
    for entry_path in entries:
        try:
            text = Path(entry_path).read_text(encoding="utf-8")
            parts.append(f"--- {Path(entry_path).stem} ---\n{text}")
        except Exception:  # noqa: BLE001
            pass
    return "\n\n".join(parts) if parts else "[no past entries found]"


# ---------------------------------------------------------------------------
# Tool schemas (JSON Schema compatible)
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": (
            "Read the text content of a file on disk. "
            "Use this to load a specific journal entry by its path."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file.",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write text content to a file on disk. "
            "Use this to save a journal entry or reflection."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path where the file should be written.",
                },
                "content": {
                    "type": "string",
                    "description": "The full text content to write.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "get_past_entries",
        "description": (
            "Retrieve and concatenate the last N days of journal entries "
            "from a journal directory. Use this to inform prompts and "
            "reflections with the user's recent history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "journal_dir": {
                    "type": "string",
                    "description": "Path to the directory containing journal files.",
                },
                "n_days": {
                    "type": "integer",
                    "description": "How many days back to look.",
                    "minimum": 1,
                    "maximum": 365,
                },
            },
            "required": ["journal_dir", "n_days"],
        },
    },
]


# ---------------------------------------------------------------------------
# Dispatch helper
# ---------------------------------------------------------------------------

def _dispatch_tool(name: str, tool_input: dict[str, Any]) -> str:
    if name == "read_file":
        return _read_file(tool_input["path"])
    if name == "write_file":
        return _write_file(tool_input["path"], tool_input["content"])
    if name == "get_past_entries":
        return _get_past_entries(
            tool_input["journal_dir"],
            int(tool_input["n_days"]),
        )
    return f"[unknown tool: {name}]"


# ---------------------------------------------------------------------------
# JournalAgent
# ---------------------------------------------------------------------------

class JournalAgent:
    """AI journal assistant backed by Claude claude-sonnet-4-6.

    All three high-level methods (``generate_daily_prompt``,
    ``process_entry``, ``generate_weekly_reflection``) run the same
    agentic loop: Claude decides which tools to call, the loop executes
    them, and the cycle continues until Claude returns ``end_turn``.
    """

    def __init__(
        self,
        journal_dir: str | os.PathLike[str] = "~/journal",
        *,
        api_key: str | None = None,
        model: str = MODEL,
    ) -> None:
        self.journal_dir = str(Path(journal_dir).expanduser().resolve())
        self.storage = JournalStorage(self.journal_dir)
        self.model = model
        self.client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_daily_prompt(self) -> str:
        """Return a personalized daily journaling prompt based on recent entries."""
        system = (
            "You are a compassionate journaling assistant. "
            "Your job is to generate a single, thoughtful daily journaling prompt "
            "that feels personal and relevant to this user's recent writing. "
            "Use the get_past_entries tool to retrieve the last 7 days of entries "
            "before crafting the prompt. "
            "Return ONLY the prompt text — no preamble, no explanation."
        )
        user_msg = (
            f"Please generate today's personalized journal prompt. "
            f"The journal directory is: {self.journal_dir}"
        )
        return self._run_loop(system, user_msg)

    def process_entry(
        self,
        entry_text: str,
        save: bool = True,
    ) -> dict[str, Any]:
        """Accept a free-form journal entry, tag mood + themes, optionally save.

        Returns a dict with keys: ``saved_path``, ``mood``, ``themes``, ``summary``.
        """
        today_path = self.storage.today_path()

        system = (
            "You are a compassionate journaling assistant with expertise in "
            "emotional analysis. Given a journal entry: "
            "1. Identify the dominant mood (one of: joyful, content, neutral, "
            "anxious, sad, angry, excited, grateful, overwhelmed, reflective). "
            "2. Extract 2-5 key themes (short noun phrases, e.g. 'work stress', "
            "'family connection'). "
            "3. Write a one-sentence summary. "
            "4. If asked to save, use write_file to persist the annotated entry. "
            "Respond ONLY with valid JSON in this exact schema: "
            '{"mood": "...", "themes": [...], "summary": "...", "saved_path": "..."}. '
            "Use null for saved_path when not saving."
        )

        save_instruction = (
            f"Save the annotated entry to {today_path}."
            if save
            else "Do NOT save the entry to disk."
        )

        # Build the Markdown-annotated entry that will be written
        annotated_template = (
            "<!-- journal-agent annotation will be prepended here -->\n"
            + entry_text
        )

        user_msg = (
            f"Here is today's journal entry:\n\n{entry_text}\n\n"
            f"{save_instruction} "
            f"The journal directory is: {self.journal_dir}.\n"
            f"If saving, prepend YAML front-matter with mood and themes, then the original entry.\n"
            f"Target path: {today_path}"
        )

        raw = self._run_loop(system, user_msg)

        # Extract JSON even if Claude wrapped it in markdown fences
        json_str = _extract_json(raw)
        try:
            result: dict[str, Any] = json.loads(json_str)
        except json.JSONDecodeError:
            result = {
                "mood": "unknown",
                "themes": [],
                "summary": raw.strip(),
                "saved_path": str(today_path) if save else None,
            }
        return result

    def generate_weekly_reflection(self) -> str:
        """Return a narrative weekly reflection summary based on the last 7 days."""
        system = (
            "You are a thoughtful journaling assistant. "
            "Use get_past_entries to fetch the last 7 days of journal entries, "
            "then write a warm, narrative weekly reflection that: "
            "- Identifies recurring themes and emotional arcs. "
            "- Celebrates wins and acknowledges challenges. "
            "- Ends with 1-2 questions for the week ahead. "
            "Write in second person ('You ...'). Aim for 200-350 words."
        )
        user_msg = (
            f"Please generate my weekly reflection. "
            f"The journal directory is: {self.journal_dir}"
        )
        return self._run_loop(system, user_msg)

    # ------------------------------------------------------------------
    # Internal agentic loop
    # ------------------------------------------------------------------

    def _run_loop(self, system: str, user_message: str) -> str:
        """Run the Claude tool-use agentic loop and return the final text."""
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message}
        ]

        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                tools=TOOLS,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            )

            # Append assistant turn to history
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Extract text from the final response
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text
                return ""

            if response.stop_reason == "tool_use":
                tool_results: list[dict[str, Any]] = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_output = _dispatch_tool(block.name, block.input)  # type: ignore[arg-type]
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": tool_output,
                            }
                        )
                messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason — return whatever text we have
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return f"[stopped: {response.stop_reason}]"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> str:
    """Strip markdown code fences from Claude's JSON responses."""
    text = text.strip()
    for fence in ("```json", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
            if text.endswith("```"):
                text = text[:-3]
            return text.strip()
    return text
