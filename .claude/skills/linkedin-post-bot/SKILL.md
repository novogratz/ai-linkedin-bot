---
name: linkedin-post-bot
description: Maintain the AI LinkedIn bot that generates and emails three French Legal NeoTech LinkedIn post options daily. Use for content generation, schedule changes, SMTP configuration, and safe repo hygiene.
---

# LinkedIn Post Bot

## Operating Rules

- Generate draft-only batches with `.venv/bin/python main.py --week`.
- Send today's real email with `.venv/bin/python main.py --today` only when explicitly requested.
- Running `.venv/bin/python main.py` starts the daily scheduler.
- The scheduler should send one email each morning at 6:00 AM America/Toronto.

## Content Requirements

- Always generate 3 choices.
- The LinkedIn posts must be in French.
- English source titles/URLs are acceptable.
- Make posts personal, direct, and impactful.
- Avoid generic AI phrasing and corporate filler.
- Keep posts around 1400-1900 characters.
- Use 6-9 emojis and 4-6 hashtags.

## Secret Handling

- `.env` and `config.json` are local-only and must not be committed.
- Public templates are `config.example.json` and `.env.example`.
- Never expose SMTP passwords in output, logs, commits, or PR text.

## Checks

Run before finalizing changes:

```bash
.venv/bin/python -m py_compile main.py post_generator.py email_sender.py
.venv/bin/python main.py --help
git status --short
```
