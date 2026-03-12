import fitz
import os
import asyncio
from collections import defaultdict
from telegram.error import RetryAfter
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

TOKEN = "8555727406:AAGP2-fR8GCUJBOr8AhblJw0-G7WNWrOocU"
TARGET_CHAT_ID = -5240584670  # replace with your destination group ID
chat_locks = defaultdict(asyncio.Lock)

from datetime import datetime, time

ACTIVE_START = time(0, 01)
ACTIVE_END = time(23, 59)

def is_active_window():
    now = datetime.now().time()
    return ACTIVE_START <= now <= ACTIVE_END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Send me a PDF, and I will return extracted images.")

async def send_with_retry(async_func, *args, **kwargs):
    while True:
        try:
            return await async_func(*args, **kwargs)
        except RetryAfter as e:
            wait = int(e.retry_after) + 1
            await asyncio.sleep(wait)

async def send_images_batch(update: Update, context: ContextTypes.DEFAULT_TYPE, image_paths, target_chat_id: int):
    for i in range(0, len(image_paths), 10):
        chunk = image_paths[i : i + 10]
        files = []
        media = []
        try:
            for path in chunk:
                f = open(path, "rb")
                files.append(f)
                media.append(InputMediaPhoto(media=f))

            await send_with_retry(context.bot.send_media_group, chat_id=target_chat_id, media=media)
        except Exception:
            # Fallback to single sends
            for f in files:
                f.close()
            for path in chunk:
                with open(path, "rb") as f:
                    await send_with_retry(context.bot.send_photo, chat_id=target_chat_id, photo=f)
        finally:
            for f in files:
                if not f.closed:
                    f.close()
            await asyncio.sleep(0.5)

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_active_window():
        await context.bot.send_message(chat_id=chat_id, text="Service hours are 07:00-22:00. Please try again during that period.")
        return

    lock = chat_locks[chat_id]
    async with lock:
        if not update.message.document or update.message.document.mime_type != "application/pdf":
            await context.bot.send_message(chat_id=chat_id, text="Please send a PDF file.")
            return

        file = update.message.document

        if file.file_size and file.file_size > 20 * 1024 * 1024:
            await context.bot.send_message(chat_id=chat_id, text="PDF is too large (max 20MB). Please send a smaller file.")
            return

        pdf_path = "file.pdf"
        images = []

        try:
            file_obj = await file.get_file()
            await file_obj.download_to_drive(pdf_path)

            with fitz.open(pdf_path) as doc:
                for page_index in range(len(doc)):
                    page = doc[page_index]
                    image_list = page.get_images(full=True)
                    for img_index, img in enumerate(image_list):
                        xref = img[0]
                        pix = fitz.Pixmap(doc, xref)
                        img_name = f"image_{page_index}_{img_index}.png"

                        if pix.n < 5:
                            pix.save(img_name)
                        else:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                            pix.save(img_name)

                        images.append(img_name)
                        pix = None

            if not images:
                await context.bot.send_message(chat_id=chat_id, text="No images found in PDF.")
            else:
                if len(images) > 4:
                    filtered_images = images[3:-1]
                else:
                    filtered_images = []

                if not filtered_images:
                    await context.bot.send_message(chat_id=chat_id, text="PDF has fewer than 5 extracted images; nothing to send after trimming.")
                else:
                    await send_images_batch(update, context, filtered_images, TARGET_CHAT_ID)

                base_name = os.path.splitext(file.file_name or "file.pdf")[0]
                await send_with_retry(context.bot.send_message, chat_id=TARGET_CHAT_ID, text=f"{base_name}")

        except Exception as exc:
            await context.bot.send_message(chat_id=chat_id, text="Error processing PDF. Try a smaller/cleaner file.")
            raise
        finally:
            for img in images:
                if os.path.exists(img):
                    os.remove(img)
            if os.path.exists(pdf_path):
                os.remove(pdf_path)

app = (
    ApplicationBuilder()
    .token(TOKEN)
    .connect_timeout(20)
    .read_timeout(120)
    .write_timeout(120)
    .media_write_timeout(180)
    .pool_timeout(20)
    .build()
)
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Please send a PDF file.")

app.add_handler(MessageHandler(filters.ALL, fallback))

app.run_polling(timeout=120)

