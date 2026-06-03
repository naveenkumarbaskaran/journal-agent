# journal-agent-ai

An AI-powered personal journaling assistant built with the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) and Claude.

## Features

- **Personalized daily prompts** — Claude reads your recent entries and crafts a prompt that resonates with your current life.
- **Free-form entry writing** — Write naturally; Claude tags your mood and extracts key themes automatically.
- **Weekly reflections** — A warm narrative summary of your week, complete with questions to carry forward.
- **Local Markdown storage** — Entries are saved as plain `YYYY-MM-DD.md` files you own forever.

## Quick start

```bash
# 1. Install
pip install journal-agent-ai
# or from source:
pip install -e .

# 2. Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# 3. Show today's prompt
journal-agent prompt

# 4. Write today's entry
journal-agent write

# 5. Reflect on the week
journal-agent reflect --week
```

## Installation from source

```bash
git clone https://github.com/example/journal-agent-ai
cd journal-agent-ai
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Configuration

| Environment variable  | Default         | Description                            |
|-----------------------|-----------------|----------------------------------------|
| `ANTHROPIC_API_KEY`   | *(required)*    | Your Anthropic API key                 |
| `JOURNAL_DIR`         | `~/journal`     | Directory where entries are stored     |
| `JOURNAL_MODEL`       | `claude-sonnet-4-6` | Claude model to use                |

You can also pass options directly:

```bash
journal-agent --journal-dir /path/to/journal --model claude-sonnet-4-6 write
```

## CLI reference

### `journal-agent prompt`

Fetches the last 7 days of entries and generates a personalized prompt for today.

```
journal-agent prompt
```

### `journal-agent write`

Shows the daily prompt, then opens an interactive writing session. After you finish (Ctrl-D / Ctrl-Z), the entry is:

- Analysed for **mood** (one of: joyful, content, neutral, anxious, sad, angry, excited, grateful, overwhelmed, reflective)
- Tagged with **themes** (2-5 short noun phrases)
- **Saved** to `~/journal/YYYY-MM-DD.md` with YAML front-matter

```
journal-agent write
journal-agent write --no-prompt   # skip the daily prompt step
```

### `journal-agent reflect --week`

Reads the last 7 days of entries and returns a narrative weekly reflection.

```
journal-agent reflect --week
```

## Entry format

Each saved entry is a Markdown file with optional YAML front-matter:

```markdown
---
date: 2024-03-15
mood: reflective
themes: ["creative work", "morning routine", "uncertainty"]
---

Today I woke up early and spent an hour sketching before work...
```

## Programmatic usage

```python
from journal_agent import JournalAgent

agent = JournalAgent(journal_dir="~/journal")

# Get today's prompt
daily_prompt = agent.generate_daily_prompt()
print(daily_prompt)

# Process and save an entry
result = agent.process_entry("Today was full of unexpected meetings...", save=True)
print(result["mood"])    # e.g. "anxious"
print(result["themes"])  # e.g. ["work stress", "time management"]

# Weekly reflection
reflection = agent.generate_weekly_reflection()
print(reflection)
```

## Architecture

```
journal_agent/
  __init__.py      re-exports JournalAgent, JournalStorage
  agent.py         JournalAgent + agentic tool-use loop
  storage.py       JournalStorage — save/load dated Markdown files
  cli.py           Click + Rich CLI (prompt / write / reflect)
```

`JournalAgent._run_loop` implements a standard Claude tool-use loop:

1. Send the user message (+ system prompt) to `claude-sonnet-4-6`.
2. If `stop_reason == "tool_use"`, dispatch each requested tool locally and send back `tool_result` blocks.
3. Repeat until `stop_reason == "end_turn"`, then return the final text block.

Three tools are exposed to the model:

| Tool | Description |
|------|-------------|
| `read_file(path)` | Read any file from disk |
| `write_file(path, content)` | Write content to a file |
| `get_past_entries(journal_dir, n_days)` | Fetch last N days of entries |

## Requirements

- Python 3.10+
- `anthropic >= 0.40.0`
- `click >= 8.1.0`
- `rich >= 13.0.0`

## License

MIT
