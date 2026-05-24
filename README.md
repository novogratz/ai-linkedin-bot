# AI LinkedIn Bot

Daily LinkedIn post generator for Elizabeth K. Flannery, focused on Legal NeoTech Marketing.

The bot uses a local Ollama model to generate three French LinkedIn post options every morning, saves each option as Markdown, and emails the three choices in one formatted HTML email.

## What It Does

- Generates 3 LinkedIn post options per run.
- Writes posts in French with a personal, executive tone.
- Uses recent legal tech, AI governance, privacy, and GenAI source context.
- Sends one daily email at 6:00 AM America/Toronto.
- Saves generated drafts in `posts/`.
- Logs to console and `logs/daily_linkedin_bot.log`.
- Keeps credentials out of git via `.env`.

## Requirements

- Python 3.11+
- Ollama running locally on port `11434`
- Gmail app password or another SMTP provider

Install Python dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Start Ollama and make sure the configured model exists:

```bash
ollama serve
ollama pull llama3.1
```

## Configuration

Create local config and env files:

```bash
cp config.example.json config.json
cp .env.example .env
```

Edit `.env`:

```bash
SMTP_USERNAME=your-gmail-address@gmail.com
SMTP_PASSWORD=your-google-app-password
SMTP_FROM_EMAIL=your-gmail-address@gmail.com
```

`config.json` is intentionally ignored by git. Use `config.example.json` as the safe committed template.

## Usage

Generate and email today's three options:

```bash
.venv/bin/python main.py --today
```

Generate seven days of drafts without emailing:

```bash
.venv/bin/python main.py --week
```

Regenerate the latest saved post date and email three new options:

```bash
.venv/bin/python main.py --regenerate
```

Run the daily scheduler:

```bash
.venv/bin/python main.py
```

The scheduler runs every day at `06:00` in `America/Toronto`.

## Safety Notes

- Do not commit `.env`, `config.json`, `posts/`, or `logs/`.
- Do not paste Gmail app passwords into issues, commits, PRs, or chat.
- The default workflow sends real email when using `--today`, `--regenerate`, or scheduler mode.
- Use `--week` when you only want drafts saved locally.

## Project Structure

```text
main.py              CLI, scheduler, config/env loading
post_generator.py    Ollama prompting, validation, Markdown saving
email_sender.py      SMTP and HTML email delivery
config.example.json  Safe config template
.env.example         Safe env template
requirements.txt     Python dependencies
```
