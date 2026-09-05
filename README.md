# Telegram → YouTube Uploader

Automatically upload videos from a Telegram channel or group to YouTube — with the caption turned into the title, description and tags. Built with n8n, Telethon and the YouTube Data API.

> Post a video in your Telegram channel → it appears on your YouTube channel, fully titled and tagged.

---

## Overview

| Step | Description |
|---|---|
| **Video detection** | An n8n Telegram Trigger watches the channel for new video messages |
| **Caption parsing** | The first caption line becomes the title, the rest the description, and `#hashtags` become YouTube tags |
| **Download** | A Python service downloads the video via Telethon (MTProto) — no 20 MB bot limit, any size works |
| **Upload** | The same service uploads to YouTube via the Data API (resumable upload) |
| **Notify** | The YouTube link is posted back to the channel |

---

## Architecture

The project has two parts that work together:

```
Telegram channel
      │  (new video)
      ▼
n8n workflow ── Telegram Trigger
      │            └─ Extract Video Info (Code)
      │                  └─ Is Video? (IF)
      │                        └─ HTTP Request ──►  Python service  ──►  YouTube
      │                                              (FastAPI)             (Data API)
      │
      └─ Notify Success (Telegram) ◄── YouTube link ──┘
```

### Why two parts?

- **n8n** handles the trigger and orchestration (detecting new messages, parsing captions, sending notifications).
- **Python service** does the heavy lifting that n8n can't: downloading large files from Telegram (the n8n Telegram node uses the Bot API, which caps downloads at 20 MB) and uploading to YouTube (the n8n YouTube node doesn't support uploads).

---

## Tech stack

| Technology | Role |
|---|---|
| **n8n** | Workflow orchestration and trigger |
| **Telethon** | Telegram MTProto client (large-file download) |
| **FastAPI** | Python service HTTP API |
| **YouTube Data API v3** | Video upload (resumable) |
| **Google OAuth 2.0** | YouTube authorization |
| **Docker** | Self-hosting |

---

## Prerequisites

- A **Telegram bot** (create one via [@BotFather](https://t.me/BotFather)) added as an **admin** to your channel/group
- **Telegram API credentials** (`api_id` + `api_hash`) from [my.telegram.org](https://my.telegram.org)
- A **Google Cloud project** with the **YouTube Data API v3** enabled and an **OAuth 2.0 client** (Desktop app type)
- A running **n8n** instance
- **Docker** (for the Python service)

---

## Setup

### 1. Google OAuth (one-time)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → create a project.
2. Enable **YouTube Data API v3**.
3. Create an **OAuth consent screen** (External) and add your email as a test user.
4. Create an **OAuth client ID** of type **Desktop app**.
5. Run the authorize step to get a refresh token:

```bash
python authorize_google.py
```

This opens a browser; approve the access and copy the printed refresh token into `.env`.

### 2. Configure the environment

```bash
cp .env.example .env
```

Fill in:

| Variable | Source |
|---|---|
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | [my.telegram.org](https://my.telegram.org) |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHANNEL_ID` | Your channel/group ID (supergroups start with `-100`) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google Cloud → Credentials |
| `GOOGLE_REFRESH_TOKEN` | From the authorize step |

### 3. Run the Python service

```bash
docker build -t yt-upload .
docker run -d --name yt-upload -p 8001:8000 --env-file .env yt-upload
```

Verify it's up:

```bash
curl http://localhost:8001/health
# → {"status":"ok"}
```

### 4. Import the n8n workflow

1. Download `telegram-to-youtube-uploader.workflow.json`.
2. In n8n, go to **Workflows → Import from File**.
3. Configure:
   - **Telegram Trigger** and **Notify Success** → your bot token
   - **Upload to YouTube** (HTTP Request) → the URL of your Python service (e.g. `http://YOUR_HOST:8001/upload`)
   - Replace `YOUR_CHAT_ID` with your channel/group ID
4. Activate the workflow.

---

## How captions map to YouTube

Given a Telegram caption like:

```
My awesome video
This is the description line.
#tutorial #python
```

The result on YouTube:

| Field | Value |
|---|---|
| **Title** | `My awesome video` |
| **Description** | `This is the description line.` |
| **Tags** | `tutorial`, `python` |

---

## API

The Python service exposes:

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/upload` | POST | Download a video and upload it to YouTube |

`POST /upload` body:

```json
{
  "message_id": 1234,
  "title": "Optional override",
  "description": "Optional override",
  "tags": ["optional", "override"]
}
```

---

## License

[MIT](LICENSE)
