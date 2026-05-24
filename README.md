# AI LinkedIn Bot

Daily LinkedIn post generator for Elizabeth K. Flannery, Director of Marketing at [Neolegal](https://www.neolegal.ca).

Uses a local Ollama model to generate one French LinkedIn post every morning, saves it as Markdown, and emails it in formatted HTML.

## What It Does

- Generates **1 post** per run (marketing voice, promotes Neolegal naturally).
- Writes posts in French — personal, direct, adds something new to the conversation.
- Uses "produits juridiques" (never "services juridiques").
- No hashtags. 6-9 emojis. 1800-2500 characters.
- Saves drafts in `posts/` and logs to `logs/`.
- Keeps credentials out of git via `.env`.

## Requirements

- Python 3.11+
- Ollama running locally on port `11434`
- Gmail app password or another SMTP provider

Install dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Start Ollama and pull the model:

```bash
ollama serve
ollama pull llama3.1
```

## Configuration

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

## Usage

Run the scheduler (fires one post immediately, then daily at 6 AM):

```bash
./run.sh
```

Or run with logging:

```bash
./run.sh 2>&1 | tee -a logs/run.log
```

Background it:

```bash
nohup ./run.sh > /dev/null 2>&1 &
```

**Other commands:**

```bash
.venv/bin/python main.py --today          # Generate and email one post now
.venv/bin/python main.py --week           # Generate 7 days of drafts without emailing
.venv/bin/python main.py --regenerate     # Regenerate the most recent post
```

### launchd (macOS auto-start at 6 AM)

```bash
cp com.neolegal.daily-linkedin-bot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.neolegal.daily-linkedin-bot.plist
```

## Safety Notes

- Do not commit `.env`, `config.json`, `posts/`, or `logs/`.
- The default workflow sends real email with `--today`, `--regenerate`, or scheduler mode.
- Use `--week` when you only want drafts saved locally.

## Project Structure

```text
main.py              CLI, scheduler, config/env loading
post_generator.py    Ollama prompting, validation, Markdown saving
email_sender.py      SMTP and HTML email delivery
run.sh               Convenience wrapper with logging
config.example.json  Safe config template
.env.example         Safe env template
requirements.txt     Python dependencies
```
