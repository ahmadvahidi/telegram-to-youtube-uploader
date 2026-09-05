"""YouTube upload service — HTTP API that n8n calls.

n8n Telegram Trigger detects a new video, then calls:
    POST /upload  {message_id, title, description, tags}

This service downloads the video from Telegram (MTProto, no 20MB limit)
and uploads it to YouTube (resumable).

Run:  python service.py
"""
import os
import asyncio
import tempfile
import re

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

from telethon import TelegramClient

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ---------- Config ----------
API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = int(os.environ["TELEGRAM_CHANNEL_ID"])
GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
GOOGLE_CLIENT_SECRET = os.environ["GOOGLE_CLIENT_SECRET"]
GOOGLE_REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN", "")
SERVICE_API_TOKEN = os.environ.get("SERVICE_API_TOKEN", "")

SESSION = os.environ.get("TELEGRAM_SESSION", "/app/bot_session")

app = FastAPI(title="YouTube Upload Service")


class UploadRequest(BaseModel):
    message_id: int
    title: str = ""
    description: str = ""
    tags: list[str] = []


def get_youtube_service():
    creds = Credentials(
        token=None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
    )
    return build("youtube", "v3", credentials=creds)


def parse_caption(text: str):
    if not text:
        return "Untitled", "", []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    title = lines[0] if lines else "Untitled"
    tags = re.findall(r"#([\p{L}_][\p{L}\p{N}_]*)", text)
    desc_lines = [l for l in lines[1:] if not l.startswith("#")]
    description = "\n".join(desc_lines)
    return title, description, tags


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload(req: UploadRequest, x_api_token: str = Header(default="")):
    if SERVICE_API_TOKEN and x_api_token != SERVICE_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start(bot_token=BOT_TOKEN)

    try:
        msg = await client.get_messages(CHANNEL_ID, ids=req.message_id)
        if msg is None:
            raise HTTPException(status_code=404, detail="Message not found")
        if not (msg.video or msg.document):
            raise HTTPException(status_code=400, detail="Message has no video")

        caption = msg.message or ""
        title, description, tags = parse_caption(caption)
        if req.title:
            title = req.title
        if req.description:
            description = req.description
        if req.tags:
            tags = req.tags

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        tmp_path = tmp.name
        tmp.close()

        try:
            path = await client.download_media(msg, file=tmp_path)
            if path is None:
                raise HTTPException(status_code=500, detail="Download failed")

            size_mb = os.path.getsize(path) / (1024 * 1024)

            youtube = get_youtube_service()
            body = {
                "snippet": {
                    "title": title[:100],
                    "description": description[:5000],
                    "tags": tags,
                    "categoryId": "22",
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                },
            }
            media = MediaFileUpload(path, mimetype="video/*", resumable=True)
            request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

            response = None
            while response is None:
                status, response = request.next_chunk()

            video_id = response["id"]
            return {
                "status": "success",
                "video_id": video_id,
                "url": f"https://youtu.be/{video_id}",
                "title": title,
                "size_mb": round(size_mb, 1),
            }
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    finally:
        await client.disconnect()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("SERVICE_PORT", 8000)))
