"""
Telegram-бот для скачивания видео из Instagram Reels и постов.
Автор: Senior Python Developer (для Вайб-кодера)
Стек: Python 3.11+, aiogram 3.x, yt-dlp, aiohttp (для Render Web Service), python-dotenv

Новые возможности:
1. Мультиязычность: Русский (RU), Английский (EN), Турецкий (TR).
2. Автоопределение языка пользователя (message.from_user.language_code).
3. Проверка лимита Telegram 50 МБ.
4. Умный обход >50 МБ: если файл слишком тяжелый, бот дает прямую ссылку на видео!
5. Полная гигиена памяти через tempfile + try...finally.
6. Встроенный aiohttp веб-сервер для бесплатного деплоя на Render Web Service.
"""

import asyncio               # Асинхронное выполнение задач без блокировки бота
import logging               # Вывод логов и ошибок в консоль
import os                    # Чтение переменных окружения (.env, PORT)
import re                    # Регулярные выражения для поиска ссылок Instagram
import shutil                # Удаление временных папок с диска
import tempfile              # Создание уникальных временных папок
from pathlib import Path     # Удобная работа с путями файлов
from typing import Dict, Any, Optional

# Сторонние библиотеки
from dotenv import load_dotenv                        # Чтение файла .env
from aiohttp import web                               # Веб-сервер для прохождения проверки Render
from aiogram import Bot, Dispatcher, F                # Главные классы aiogram 3.x
from aiogram.filters import CommandStart, Command     # Фильтры команд /start, /help, /lang
from aiogram.types import (
    Message, 
    FSInputFile, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery
)                                                     # Типы сообщений и кнопки
from aiogram.enums import ChatAction                  # Статус 'отправляет видео...'
import yt_dlp                                         # Библиотека для скачивания видео


# ==============================================================================
# 1. ЗАГРУЗКА НАСТРОЕК И ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
# ==============================================================================

# Загружаем переменные из локального файла .env (если он есть)
load_dotenv()

# Считываем токен бота из настроек
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError(
        "❌ ОШИБКА: Переменная BOT_TOKEN не найдена!\n"
        "Укажите BOT_TOKEN в файле .env или в Environment Variables на Render."
    )

# Лимит Telegram Bot API на отправку файлов (50 Мегабайт)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


# ==============================================================================
# 2. МУЛЬТИЯЗЫЧНЫЙ СЛОВАРЬ (РУССКИЙ, ENGLISH, TÜRKÇE)
# ==============================================================================

MESSAGES: Dict[str, Dict[str, str]] = {
    "ru": {
        "welcome": (
            "👋 **Привет, {name}!**\n\n"
            "Я бот для быстрого скачивания видео и Reels из **Instagram**.\n\n"
            "🚀 **Как пользоваться:**\n"
            "1. Открой Instagram и скопируй ссылку на любой **Reels** или пост.\n"
            "2. Просто отправь ссылку сюда в чат.\n"
            "3. Я скачаю видео в оригинальном качестве и пришлю тебе!\n\n"
            "💡 *Пример ссылки:* `https://www.instagram.com/reel/C3b4XK7yM/`\n"
            "🌐 Сменить язык: /lang"
        ),
        "help": (
            "ℹ️ **Справка по боту:**\n\n"
            "• Бот скачивает только с **публичных** аккаунтов (закрытые профили недоступны).\n"
            "• Стандартный лимит Telegram для ботов — **50 МБ**.\n"
            "• Если видео весит больше 50 МБ, бот пришлет прямую ссылку на скачивание.\n"
            "• Все файлы удаляются с сервера сразу после отправки."
        ),
        "no_link": (
            "🤔 В твоем сообщении нет ссылки на Instagram.\n"
            "Пожалуйста, пришли ссылку в формате: `https://www.instagram.com/reel/...`"
        ),
        "downloading": "⏳ **Загружаю видео из Instagram...** Пожалуйста, подожди пару секунд.",
        "uploading": "📤 **Отправляю видео в чат...**",
        "caption": "✨ Приятного просмотра!\n🤖 Скачано через @{bot_name}",
        "too_big": (
            "⚠️ **Видео слишком большое для отправки в Telegram!**\n\n"
            "📊 Размер файла: **{size:.1f} МБ** (Лимит Telegram: 50 МБ).\n"
            "Telegram Bot API не разрешает ботам отправлять файлы больше 50 МБ.\n\n"
            "🌐 **Но ты можешь скачать его напрямую по ссылке ниже:**"
        ),
        "too_big_btn": "⬇️ Открыть и скачать видео ({size:.1f} МБ)",
        "err_download": (
            "❌ **Не удалось скачать видео.**\n\n"
            "Возможные причины:\n"
            "• Профиль автора является закрытым (приватным).\n"
            "• Видео удалено или ссылка недействительна.\n"
            "• Instagram временно ограничил запрос."
        ),
        "err_general": "⚠️ Произошла непредвиденная ошибка. Попробуй отправить ссылку еще раз чуть позже.",
        "lang_choose": "🌐 **Выберите язык / Choose language / Dil seçin:**",
        "lang_switched": "✅ Язык успешно изменен на Русский!"
    },
    "en": {
        "welcome": (
            "👋 **Hello, {name}!**\n\n"
            "I am a bot for downloading **Instagram** videos and Reels.\n\n"
            "🚀 **How to use:**\n"
            "1. Open Instagram and copy the link to any **Reels** or post.\n"
            "2. Just send the link into this chat.\n"
            "3. I will download the video in top quality and send it to you!\n\n"
            "💡 *Example:* `https://www.instagram.com/reel/C3b4XK7yM/`\n"
            "🌐 Change language: /lang"
        ),
        "help": (
            "ℹ️ **Bot Help & Info:**\n\n"
            "• Downloading works for **public** accounts only.\n"
            "• The standard Telegram limit for bots is **50 MB**.\n"
            "• If a video exceeds 50 MB, the bot provides a direct download link.\n"
            "• Temporary files are deleted from the server immediately after delivery."
        ),
        "no_link": (
            "🤔 No Instagram link detected in your message.\n"
            "Please send a link formatted like: `https://www.instagram.com/reel/...`"
        ),
        "downloading": "⏳ **Downloading video from Instagram...** Please wait a few seconds.",
        "uploading": "📤 **Uploading video to Telegram...**",
        "caption": "✨ Enjoy watching!\n🤖 Downloaded with @{bot_name}",
        "too_big": (
            "⚠️ **The video is too large to send via Telegram!**\n\n"
            "📊 File size: **{size:.1f} MB** (Telegram limit is 50 MB).\n"
            "Telegram Bot API forbids bots from uploading files over 50 MB.\n\n"
            "🌐 **However, you can watch or download it directly using the link below:**"
        ),
        "too_big_btn": "⬇️ Open & Download Video ({size:.1f} MB)",
        "err_download": (
            "❌ **Failed to download the video.**\n\n"
            "Possible reasons:\n"
            "• The author's profile is private.\n"
            "• The video was deleted or the link is invalid.\n"
            "• Instagram temporarily restricted access."
        ),
        "err_general": "⚠️ An unexpected error occurred. Please try again with another link in a few moments.",
        "lang_choose": "🌐 **Choose language / Выберите язык / Dil seçin:**",
        "lang_switched": "✅ Language successfully switched to English!"
    },
    "tr": {
        "welcome": (
            "👋 **Merhaba, {name}!**\n\n"
            "Ben **Instagram** video ve Reels indirme botuyum.\n\n"
            "🚀 **Nasıl kullanılır:**\n"
            "1. Instagram'ı aç ve herhangi bir **Reels** veya video gönderisinin bağlantısını kopyala.\n"
            "2. Bağlantıyı bu sohbete gönder.\n"
            "3. Videoyu en yüksek kalitede indirip sana göndereyim!\n\n"
            "💡 *Örnek link:* `https://www.instagram.com/reel/C3b4XK7yM/`\n"
            "🌐 Dili değiştir: /lang"
        ),
        "help": (
            "ℹ️ **Bot Yardım Bilgisi:**\n\n"
            "• İndirme yalnızca **herkese açık** (gizli olmayan) hesaplar için çalışır.\n"
            "• Telegram botları için dosya boyutu sınırı **50 MB**'dir.\n"
            "• Video 50 MB'den büyükse, bot sana doğrudan tarayıcıdan indirme bağlantısı verir.\n"
            "• Sunucudaki geçici dosyalar gönderimden hemen sonra silinir."
        ),
        "no_link": (
            "🤔 Mesajında geçerli bir Instagram bağlantısı bulunamadı.\n"
            "Lütfen şu formatta bir link gönder: `https://www.instagram.com/reel/...`"
        ),
        "downloading": "⏳ **Instagram videosu indiriliyor...** Lütfen birkaç saniye bekle.",
        "uploading": "📤 **Video sohbete yükleniyor...**",
        "caption": "✨ İyi seyirler!\n🤖 @{bot_name} ile indirildi",
        "too_big": (
            "⚠️ **Video Telegram'a yüklemek için çok büyük!**\n\n"
            "📊 Dosya boyutu: **{size:.1f} MB** (Telegram sınırı: 50 MB).\n"
            "Telegram Bot API'si 50 MB üzerindeki dosyaların bota yüklenmesine izin vermez.\n\n"
            "🌐 **Ancak videoyu aşağıdaki doğrudan bağlantıdan indirebilirsin:**"
        ),
        "too_big_btn": "⬇️ Videoyu Aç ve İndir ({size:.1f} MB)",
        "err_download": (
            "❌ **Video indirilemedi.**\n\n"
            "Olası nedenler:\n"
            "• Profil gizli (özel).\n"
            "• Video silinmiş veya bağlantı geçersiz.\n"
            "• Instagram geçici olarak kısıtlama uyguladı."
        ),
        "err_general": "⚠️ Beklenmeyen bir hata oluştu. Lütfen biraz sonra tekrar deneyin.",
        "lang_choose": "🌐 **Dil seçin / Выберите язык / Choose language:**",
        "lang_switched": "✅ Dil başarıyla Türkçe olarak ayarlandı!"
    }
}

USER_LANGUAGE_PREFERENCES: Dict[int, str] = {}


def get_user_language(user_id: int, user_language_code: Optional[str]) -> str:
    if user_id in USER_LANGUAGE_PREFERENCES:
        return USER_LANGUAGE_PREFERENCES[user_id]
    if user_language_code:
        code = user_language_code.lower()
        if code.startswith("ru"):
            return "ru"
        if code.startswith("tr"):
            return "tr"
    return "en"


def get_text(key: str, lang: str, **kwargs) -> str:
    locale_dict = MESSAGES.get(lang, MESSAGES["en"])
    template = locale_dict.get(key, MESSAGES["en"].get(key, ""))
    return template.format(**kwargs) if kwargs else template


def build_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang:ru"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang:en"),
                InlineKeyboardButton(text="🇹🇷 Türkçe", callback_data="set_lang:tr"),
            ]
        ]
    )


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

INSTAGRAM_URL_REGEX = re.compile(
    r"(https?:\/\/(?:www\.)?instagram\.com\/(?:reel|p|tv|reels)\/[\w\-\?=\&]+)",
    re.IGNORECASE
)


async def handle_ping(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "online",
        "service": "Instagram Downloader Telegram Bot",
        "version": "2.0-multilang"
    })


async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)

    port = int(os.getenv("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logger.info(f"🌐 Сервер проверки Render активен на порту {port}")
    return runner


def sync_download_instagram_media(url: str, download_folder: Path) -> Dict[str, Any]:
    output_template = str(download_folder / "%(id)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        direct_url = info.get("url")
        if not direct_url and "formats" in info:
            formats = info.get("formats", [])
            if formats:
                direct_url = formats[-1].get("url")

        downloaded_file = Path(ydl.prepare_filename(info))
        if not downloaded_file.exists():
            files = list(download_folder.glob("*.*"))
            if files:
                downloaded_file = files[0]
            else:
                raise FileNotFoundError("Не удалось найти скачанный файл на диске.")

        return {
            "file_path": downloaded_file,
            "direct_url": direct_url,
            "file_size": downloaded_file.stat().st_size
        }


@dp.message(CommandStart())
async def handle_start(message: Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Friend"
    lang = get_user_language(user_id, message.from_user.language_code)

    welcome_text = get_text("welcome", lang, name=user_name)
    await message.answer(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=build_language_keyboard()
    )


@dp.message(Command("help"))
async def handle_help(message: Message):
    user_id = message.from_user.id
    lang = get_user_language(user_id, message.from_user.language_code)
    await message.answer(get_text("help", lang), parse_mode="Markdown")


@dp.message(Command("lang"))
async def handle_lang_command(message: Message):
    user_id = message.from_user.id
    lang = get_user_language(user_id, message.from_user.language_code)
    await message.answer(
        get_text("lang_choose", lang),
        parse_mode="Markdown",
        reply_markup=build_language_keyboard()
    )


@dp.callback_query(F.data.startswith("set_lang:"))
async def handle_language_selection(callback: CallbackQuery):
    new_lang = callback.data.split(":")[1]
    user_id = callback.from_user.id
    USER_LANGUAGE_PREFERENCES[user_id] = new_lang

    await callback.answer()
    await callback.message.edit_text(
        get_text("lang_switched", new_lang),
        parse_mode="Markdown"
    )


@dp.message(F.text)
async def handle_instagram_link(message: Message):
    user_id = message.from_user.id
    lang = get_user_language(user_id, message.from_user.language_code)
    user_text = message.text.strip()

    match = INSTAGRAM_URL_REGEX.search(user_text)
    if not match:
        await message.reply(get_text("no_link", lang), parse_mode="Markdown")
        return

    instagram_url = match.group(0)
    status_msg = await message.reply(get_text("downloading", lang), parse_mode="Markdown")
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)

    temp_dir = Path(tempfile.mkdtemp(prefix="insta_download_"))

    try:
        media_data = await asyncio.to_thread(
            sync_download_instagram_media,
            instagram_url,
            temp_dir
        )

        file_path: Path = media_data["file_path"]
        file_size_bytes: int = media_data["file_size"]
        file_size_mb = file_size_bytes / (1024 * 1024)
        direct_url: Optional[str] = media_data.get("direct_url")

        # ПРОВЕРКА ЛИМИТА 50 МБ
        if file_size_bytes > MAX_FILE_SIZE_BYTES:
            logger.warning(f"Файл {file_size_mb:.2f} МБ превышает 50 МБ.")
            warning_text = get_text("too_big", lang, size=file_size_mb)

            reply_markup = None
            if direct_url:
                btn_text = get_text("too_big_btn", lang, size=file_size_mb)
                reply_markup = InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text=btn_text, url=direct_url)]]
                )

            await status_msg.edit_text(
                warning_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            return

        # ОТПРАВКА ВИДЕО
        await status_msg.edit_text(get_text("uploading", lang), parse_mode="Markdown")

        bot_info = await bot.get_me()
        bot_username = bot_info.username or "InstagramBot"
        caption_text = get_text("caption", lang, bot_name=bot_username)

        video_input = FSInputFile(path=file_path)
        await message.answer_video(
            video=video_input,
            caption=caption_text,
            supports_streaming=True
        )
        await status_msg.delete()

    except yt_dlp.utils.DownloadError as download_err:
        logger.error(f"Ошибка загрузки Instagram: {download_err}")
        await status_msg.edit_text(get_text("err_download", lang), parse_mode="Markdown")

    except Exception as err:
        logger.exception(f"Непредвиденная ошибка: {err}")
        await status_msg.edit_text(get_text("err_general", lang), parse_mode="Markdown")

    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"🧹 Временные файлы удалены: {temp_dir}")


async def main():
    logger.info("🚀 Запуск мультиязычного Instagram Telegram бота...")
    web_runner = await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        await dp.start_polling(bot)
    finally:
        await web_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Бот остановлен.")
