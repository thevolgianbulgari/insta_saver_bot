"""
Telegram-бот для скачивания видео из Instagram Reels и постов.
Автор: Senior Python Developer (для Вайб-кодера)
Стек: Python 3.11+, aiogram 3.x, yt-dlp, aiohttp (для бесплатного Render Web Service), python-dotenv
"""

import asyncio               # Библиотека для асинхронного программирования (не блокирует бота)
import logging               # Модуль для логирования событий и ошибок в консоль
import os                    # Модуль для работы с операционной системой и переменными окружения
import re                    # Модуль для регулярных выражений (поиск ссылок Instagram)
import shutil                # Для удаления временных папок после скачивания
import tempfile              # Для создания изолированных временных файлов
from pathlib import Path     # Объектно-ориентированная работа с путями файлов

# Сторонние библиотеки
from dotenv import load_dotenv                        # Загрузка переменных из файла .env
from aiohttp import web                               # Встроенный в экосистему aiogram легковесный веб-сервер
from aiogram import Bot, Dispatcher, F                # Главные классы фреймворка aiogram 3.x
from aiogram.filters import CommandStart, Command     # Фильтры для команд /start и /help
from aiogram.types import Message, FSInputFile        # Типы сообщений и отправка локального файла
from aiogram.enums import ChatAction                  # Статусы действий ("отправляет видео...")
import yt_dlp                                         # Библиотека для скачивания видео из Instagram


# ==============================================================================
# 1. ЗАГРУЗКА НАСТРОЕК И ПРОВЕРКА ТОКЕНА
# ==============================================================================

# Загружаем переменные из локального файла .env (если он есть)
load_dotenv()

# Получаем токен Telegram-бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError(
        "❌ ОШИБКА: Переменная BOT_TOKEN не найдена!\n"
        "Создайте файл .env и добавьте туда: BOT_TOKEN=ваш_токен\n"
        "Либо укажите BOT_TOKEN в настройках Environment Variables на Render."
    )


# ==============================================================================
# 2. ИНИЦИАЛИЗАЦИЯ ЛОГИРОВАНИЯ И СУЩНОСТЕЙ AIOGRAM
# ==============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Регулярное выражение для поиска ссылок Instagram
INSTAGRAM_URL_REGEX = re.compile(
    r"(https?:\/\/(?:www\.)?instagram\.com\/(?:reel|p|tv|reels)\/[\w\-\?=\&]+)",
    re.IGNORECASE
)

# Ограничение размера файла Telegram Bot API (50 МБ)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


# ==============================================================================
# 3. ВЕБ-СЕРВЕР ДЛЯ БЕСПЛАТНОГО RENDER WEB SERVICE (HEALTHCHECK)
# ==============================================================================

async def handle_ping(request: web.Request) -> web.Response:
    """
    Отвечает 200 OK на запросы Render Port Scanner и внешних пингеров (UptimeRobot).
    Благодаря этому Render видит открытый порт и не убивает бота по таймауту!
    """
    return web.json_response({
        "status": "online",
        "service": "Instagram Telegram Downloader Bot",
        "bot": "aiogram 3.x",
        "message": "Бот успешно запущен и слушает Telegram обновления!"
    })


async def start_web_server() -> web.AppRunner:
    """
    Запускает асинхронный HTTP-сервер на aiohttp в ТОМ ЖЕ цикле событий (Event Loop),
    что и aiogram, не расходуя лишней оперативной памяти!
    """
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)

    # Render передает номер порта через переменную окружения PORT (обычно 10000)
    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    
    # 0.0.0.0 обязательно для привязки внутри облачного контейнера Render
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logger.info(f"🌐 HTTP Healthcheck сервер запущен на 0.0.0.0:{port} для Render Web Service")
    return runner


# ==============================================================================
# 4. ФУНКЦИЯ ДЛЯ СКАЧИВАНИЯ ВИДЕО ЧЕРЕЗ YT-DLP
# ==============================================================================

def sync_download_instagram_video(url: str, download_folder: Path) -> Path:
    """
    Синхронная функция скачивания через yt-dlp.
    Запускается в отдельном потоке (asyncio.to_thread), чтобы не блокировать Event Loop.
    """
    output_template = str(download_folder / "%(id)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "max_filesize": MAX_FILE_SIZE_BYTES,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded_file = Path(ydl.prepare_filename(info))

        if not downloaded_file.exists():
            files = list(download_folder.glob("*.*"))
            if files:
                downloaded_file = files[0]
            else:
                raise FileNotFoundError("Не удалось обнаружить скачанный файл на диске.")

        return downloaded_file


# ==============================================================================
# 5. ОБРАБОТЧИКИ КОМАНД (ХЭНДЛЕРЫ)
# ==============================================================================

@dp.message(CommandStart())
async def handle_start_command(message: Message):
    """Приветствие пользователя при /start"""
    user_name = message.from_user.first_name if message.from_user else "друг"
    welcome_text = (
        f"👋 Привет, {user_name}! Я бот для скачивания видео из Instagram.\n\n"
        "🚀 **Как пользоваться:**\n"
        "1. Скопируй ссылку на любой **Instagram Reels** или **пост**.\n"
        "2. Просто отправь ссылку сюда сообщением.\n"
        "3. Я скачаю видео и пришлю его в чат без водяных знаков!\n\n"
        "💡 *Пример:* `https://www.instagram.com/reel/C3b.../`"
    )
    await message.answer(welcome_text, parse_mode="Markdown")


@dp.message(Command("help"))
async def handle_help_command(message: Message):
    """Справка по боту при /help"""
    help_text = (
        "ℹ️ **Справка:**\n\n"
        "• Бот поддерживает **Reels**, **посты** и **IGTV**.\n"
        "• Профиль автора должен быть **публичным** (не закрытым).\n"
        "• Максимальный вес видео в Telegram — 50 МБ.\n"
        "• Все видео сразу удаляются с сервера после отправки."
    )
    await message.answer(help_text, parse_mode="Markdown")


# ==============================================================================
# 6. ГЛАВНЫЙ ОБРАБОТЧИК ССЫЛОК INSTAGRAM
# ==============================================================================

@dp.message(F.text)
async def handle_instagram_link(message: Message):
    """Обработка текстового сообщения с проверкой ссылки на Instagram"""
    user_text = message.text.strip()
    match = INSTAGRAM_URL_REGEX.search(user_text)

    if not match:
        await message.reply(
            "🤔 В этом сообщении нет ссылки на Instagram.\n"
            "Пожалуйста, пришли ссылку в формате: `https://www.instagram.com/reel/...`",
            parse_mode="Markdown"
        )
        return

    instagram_url = match.group(0)
    status_msg = await message.reply("⏳ Загружаю видео из Instagram... Секундочку.")
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)

    temp_dir = Path(tempfile.mkdtemp(prefix="insta_bot_"))

    try:
        # Выносим синхронный yt-dlp в системный поток
        video_path = await asyncio.to_thread(
            sync_download_instagram_video,
            instagram_url,
            temp_dir
        )

        # Проверка лимита 50MB Telegram
        file_size = video_path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            await status_msg.edit_text(
                "⚠️ Видео слишком большое (>50 МБ). Telegram не позволяет ботам отправлять файлы свыше 50 МБ."
            )
            return

        await status_msg.edit_text("📤 Отправляю видео в чат...")

        video_file = FSInputFile(path=video_path)
        await message.answer_video(
            video=video_file,
            caption="✨ Приятного просмотра!\n🤖 Скачано с помощью @InstaLoad_app",
            supports_streaming=True
        )
        await status_msg.delete()

    except yt_dlp.utils.DownloadError as download_err:
        logger.error(f"Ошибка загрузки Instagram: {download_err}")
        await status_msg.edit_text(
            "❌ Не удалось скачать видео.\n"
            "Возможные причины:\n"
            "• Профиль автора приватный (закрытый).\n"
            "• Видео удалено или ссылка устарела.\n"
            "• Instagram временно ограничил доступ."
        )

    except Exception as err:
        logger.exception(f"Непредвиденная ошибка: {err}")
        await status_msg.edit_text(
            "⚠️ Произошла ошибка при обработке видео. Попробуйте еще раз чуть позже."
        )

    finally:
        # Гарантированное удаление временных файлов (предотвращает Disk Full на Render)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"Память очищена: {temp_dir}")


# ==============================================================================
# 7. ТОЧКА ВХОДА: ВЕБ-СЕРВЕР + POLLING
# ==============================================================================

async def main():
    logger.info("🚀 Запуск бота для Render Web Service...")

    # 1. Запуск легковесного веб-сервера для прохождения проверки портов Render
    web_runner = await start_web_server()

    # 2. Очистка старых обновлений
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        # 3. Запуск чтения сообщений из Telegram
        await dp.start_polling(bot)
    finally:
        # Корректное освобождение ресурсов при перезапуске контейнера
        await web_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Бот остановлен.")
