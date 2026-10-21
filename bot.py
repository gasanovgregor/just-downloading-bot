
import os
import re
import asyncio
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
MAX_SIZE = 45 * 1024 * 1024

ALLOWED_DOMAINS = {
    "youtube.com", "youtu.be", "youtube-nocookie.com",
    "tiktok.com", "instagram.com", "vk.com",
    "m.vk.com", "vkontakte.ru",
}


def valid_url(url):
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return (
            parsed.scheme == "https"
            and any(
                host == domain or host.endswith("." + domain)
                for domain in ALLOWED_DOMAINS
            )
        )
    except Exception:
        return False


def download_media(url, folder):
    options = {
        "outtmpl": str(Path(folder) / "%(title).70s-%(id)s.%(ext)s"),
        "format": "best[filesize<45M]/best",
        "max_filesize": MAX_SIZE,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 2,
        "socket_timeout": 25,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        if info.get("_type") == "playlist":
            raise ValueError("Отправь ссылку на отдельную публикацию.")
        files = [
            p for p in Path(folder).iterdir()
            if p.is_file()
            and not p.name.endswith((".part", ".ytdl"))
        ]
        if not files:
            raise ValueError("Не удалось получить файл.")
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        result = files[0]

        if result.stat().st_size > MAX_SIZE:
            raise ValueError("Файл слишком большой для отправки ботом.")
        return str(result), info.get("title", "Медиа")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 👋 Отправь ссылку на доступное видео, "
        "фото или другую публикацию — попробую скачать её."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Как пользоваться:\n"
        "1. Отправь ссылку на публикацию.\n"
        "2. Подожди, пока я её обработаю.\n"
        "3. Получи файл в Telegram.\n\n"
        "Поддержка зависит от платформы и доступности публикации."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    match = re.search(r"https://[^\s<>]+", message.text or "")

    if not match:
        await message.reply_text("Пришли обычную ссылку, начинающуюся с https://")
        return

    url = match.group(0).rstrip(".,!?)]}")

    if not valid_url(url):
        await message.reply_text(
            "Пока поддерживаются ссылки YouTube, TikTok, Instagram и VK."
        )
        return

    status = await message.reply_text("⏳ Пробую скачать медиа...")

    try:
        with tempfile.TemporaryDirectory() as folder:
            file_path, title = await asyncio.to_thread(
                download_media, url, folder
            )

            with open(file_path, "rb") as media:
                if Path(file_path).suffix.lower() in {
                    ".mp4", ".mov", ".webm", ".mkv"
                }:
                    await message.reply_video(
                        video=media,
                        caption=title[:900],
                        read_timeout=120,
                        write_timeout=120,
                    )
                else:
                    await message.reply_document(
                        document=media,
                        caption=title[:900],
                        read_timeout=120,
                        write_timeout=120,
                    )

        await status.delete()

    except Exception:
        await status.edit_text(
            "😕 Не получилось скачать эту публикацию. "
            "Возможно, ссылка недоступна, формат не поддерживается "
            "или файл слишком большой. Попробуй другую ссылку."
        )


def main():
    if not TOKEN:
        raise RuntimeError("Не задана переменная BOT_TOKEN.")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)
    )
    app.run_polling()


if __name__ == "__main__":
    main()
