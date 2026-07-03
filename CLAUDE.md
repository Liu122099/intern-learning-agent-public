# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Configure AI (copy the example and fill in your credentials)
cp config.example.json config.json

# Run the local web app
python app.py
# → http://localhost:5000

# Generate the static growth report
python generate_report.py
# → output/report.html
```

## What this is

A personal, self-evolving growth Agent. Beyond recording daily logs, it uses an LLM to review work weekly, track a skill model over time, and turn scattered work into reusable résumé material. Local-first, single-user, plain-file storage.

## Architecture

Flask app with flat-file storage (no database) plus a standalone report generator.

**Entry points:**
- `app.py` — Flask server. Holds all routes plus the memory / knowledge-base / projects / tools / weekly-review logic.
- `doc_parser.py` — Extracts text from PDF/Word/PPT/Markdown/txt for AI analysis.
- `generate_report.py` — Reads all data and produces a self-contained HTML report.

**Six feature modules** (all in `app.py`):
1. Daily logs — `/`, `/daily/new`, `/daily/<date>`. Markdown with frontmatter; supports multi-day logs via `date_end`.
2. AI-assisted daily writing — `/api/ai-assist`. Turns rough notes into a structured log, injecting memory + knowledge context.
3. Knowledge base — `/upload`. Uploaded docs → AI categorize/summarize → `knowledge.json`.
4. Project portfolio — `/projects`. Project docs → AI extracts achievements/metrics/skills → `projects.json`.
5. Tools box — `/tools`. Upload zip tools; auto-reads the README inside as description → `tools.json`.
6. Weekly review + dashboard — `/review`, `/dashboard`, `/api/review`. AI reviews a week of logs, scores growth, gives advice, and writes back to memory.

**The memory loop (the core idea):** weekly review reads the week's logs → AI analysis → `update_memory_from_review` / `update_memory_advice` write back to `memory.json` (skill scores, advice tracker, growth log) → `get_memory_context` feeds that history back into the next AI call. Knowledge and projects context are injected the same way.

**Data layer** — all state under `data/`:
- `data/daily/{YYYY-MM-DD}.md` — daily logs (frontmatter + Markdown body)
- `data/docs/` — knowledge-base source files
- `data/projects/` — project source files
- `data/tools/` — tool zip packages
- `data/reviews/{week-monday}.json` — weekly review results
- `data/memory.json` — profile, 8-dim skill_model, advice_tracker, growth_log, milestones, meta
- `data/knowledge.json` / `projects.json` / `tools.json` / `tags.json` — indexes

**Frontmatter format** for daily logs:
```markdown
---
title: 标题
tags: 标签1, 标签2
date: 2024-01-15
date_end: 2024-01-17   # optional, for multi-day logs
---

正文内容 (Markdown)
```

## AI / LLM integration

- `call_llm(prompt, system)` in `app.py` calls an OpenAI-compatible endpoint at `{base_url}/v1/chat/completions`.
- Config via `load_config()`: **environment variables override `config.json`**. Vars: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`. Returns `None` if incomplete; callers degrade gracefully.
- `config.json` holds your key and is gitignored — never commit it, never echo the key value.
- LLM JSON responses are parsed defensively (strips `<think>` tags and code fences, then regex-extracts the `{...}`). This pattern appears in `process_uploaded_file` and `process_project_file` — a candidate for a shared helper.

## Key Conventions

- All file I/O uses `encoding='utf-8'`.
- Daily filenames are the date: `{YYYY-MM-DD}.md`. Writing the same date overwrites silently.
- **Tag splitting must use `split_tags()`** (handles `, ， ; ； 、`). Do not `.split(',')`.
- **Frontmatter parsing must use `parse_frontmatter()`** — it tolerates missing/broken closing `---` instead of raising. `get_all_dailies()` skips files that fail to parse rather than 500-ing.
- Avoid emoji in `print()` — the Windows GBK console raises `UnicodeEncodeError` (use `[OK]` style instead).
- `app.run(debug=...)` is controlled by the `FLASK_DEBUG` env var, default off (the Werkzeug debugger allows RCE — never expose it).
- The report template uses Python `str.format()` with doubled braces for CSS (not Jinja2).
- `output/report.html` and `config.json` are gitignored.

**Templates** use Jinja2 with a shared visual style: Noto Serif SC font, warm accent color (#e8590c), editorial layout. Maintain this aesthetic when modifying templates.
