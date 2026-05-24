---
name: linkedin-post-bot
description: Operate and maintain this AI LinkedIn bot repository. Use when generating Legal NeoTech LinkedIn drafts, changing schedule/email behavior, handling config secrets, or preparing safe commits/pushes for this repo.
---

# LinkedIn Post Bot

## Core Workflow

- Use `.venv/bin/python main.py --week` to generate drafts only.
- Use `.venv/bin/python main.py --today` only when the user explicitly wants to send the email now.
- Scheduler mode is `.venv/bin/python main.py`; it sends one email per day at the configured time.
- The daily email must contain 3 French post options.

## Content Rules

- Posts must be in French.
- Source/news titles and URLs may remain in English.
- Tone: personal, executive, direct, less AI-generated.
- Length target: 1400-1900 characters.
- Include 6-9 emojis.
- Include 4-6 hashtags.
- Use recent legal tech, GenAI, data privacy, or AI governance source context.

## Secrets

- Never commit `.env`, `config.json`, `posts/`, or `logs/`.
- Keep credentials in `.env`.
- Commit only `config.example.json` and `.env.example`.

## Validation

Before committing:

```bash
.venv/bin/python -m py_compile main.py post_generator.py email_sender.py
.venv/bin/python main.py --help
git status --short
```

Inspect staged files before committing to ensure no secrets are included.
