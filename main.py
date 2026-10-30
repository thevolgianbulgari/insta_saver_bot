"""
Telegram-бот для скачивания видео из Instagram Reels и постов.
Автор: Senior Python Developer (для Вайб-кодера)
Стек: Python 3.11+, aiogram 3.x, yt-dlp, python-dotenv
Готов к бесплатному деплою на Render, Koyeb или запуск на смартфоне (Termux/Pydroid).
"""

import asyncio               # Библиотека для асинхронного программирования (не блокирует бота)
import logging               # Модуль для логирования событий и ошибок в консоль
import os                    # Модуль для работы с операционной системой и переменными окружения
import re                    # Модуль для регулярных выражений (поиск ссылок Instagram)
import shutil                # Для удобного удаления временных папок при необходимости
import tempfile              # Для создания изолированных временных файлов
from pathlib import Path     # Удобная объектно-ориентированная работа с путями файлов

# Сторонние библиотеки
from dotenv import load_dotenv                        # Загрузка переменных из файла .env
from aiogram import Bot, Dispatcher, F                # Главные классы фреймворка aiogram 3.x
from aiogram.filters import CommandStart, Command     # Фильтры для команд /start и /help
from aiogram.types import Message, FSInputFile        # Типы сообщений и отправка локального файла
from aiogram.enums import ChatAction                  # Статусы действий (например: "отправляет видео...")
import yt_dlp                                         # Мощнейшая библиотека для скачивания медиа


# ==============================================================================
# 1. ЗАГРУЗКА НАСТРОЕК И ПРОВЕРКА ТОКЕНА
# ==============================================================================

# Загружаем переменные из локального файла .env (если он существует)
load_dotenv()

# Получаем токен Telegram-бота из переменных окружения
# ВАЖНО: Никогда не сохраняйте токен прямо в коде, чтобы его не украли на GitHub!
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Если токен не задан, останавливаем программу с понятным предупреждением
if not BOT_TOKEN:
    raise ValueError(
        "❌ ОШИБКА: Переменная BOT_TOKEN не найдена!\n"
        "Создайте файл .env и добавьте туда: BOT_TOKEN=ваш_токен\n"
        "Либо укажите BOT_TOKEN в настройках Environment Variables на Render/Koyeb."
    )


# ==============================================================================
# 2. ИНИЦИАЛИЗАЦИЯ ЛОГИРОВАНИЯ И СУЩНОСТЕЙ AIOGRAM
# ==============================================================================

# Настраиваем вывод логов: время, уровень (INFO) и само сообщение
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Инициализируем бота с нашим токеном
bot = Bot(token=BOT_TOKEN)

# Диспетчер — это главный распределитель входящих сообщений по обработчикам (хэндлерам)
dp = Dispatcher()

# Регулярное выражение для точного поиска ссылок на Reels, посты и видео в Instagram
INSTAGRAM_URL_REGEX = re.compile(
    r"(https?:\/\/(?:www\.)?instagram\.com\/(?:reel|p|tv|reels)\/[\w\-\?=\&]+)",
    re.IGNORECASE
)

# Ограничение размера файла для стандартных Telegram-ботов (50 МБ)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


# ==============================================================================
# 3. ФУНКЦИЯ ДЛЯ СКАЧИВАНИЯ ВИДЕО ЧЕРЕЗ YT-DLP
# ==============================================================================

def sync_download_instagram_video(url: str, download_folder: Path) -> Path:
    """
    Синхронная функция скачивания через yt-dlp.
    Мы запускаем её в отдельном потоке (asyncio.to_thread),
    чтобы бот оставался отзывчивым и не 'зависал' для других пользователей!
    """
    # Шаблон имени файла: ID видео + расширение
    output_template = str(download_folder / "%(id)s.%(ext)s")

    # Конфигурация yt-dlp для оптимальной работы с Instagram
    ydl_opts = {
        "outtmpl": output_template,              # Путь сохранения файла
        "format": "best[ext=mp4]/best",          # Приоритет формата: MP4 с лучшим качеством
        "quiet": True,                           # Не спамить системными логами в консоль
        "no_warnings": True,                     # Скрыть мелкие предупреждения
        "max_filesize": MAX_FILE_SIZE_BYTES,     # Защита от слишком больших файлов (>50MB)
        # Современный User-Agent, чтобы Instagram реже блокировал запросы
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    # Выполняем извлечение информации и скачивание
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        # Получаем итоговый путь к скачанному файлу
        downloaded_file = Path(ydl.prepare_filename(info))

        # Если расширение файла изменилось (например, объединились дорожки), находим его
        if not downloaded_file.exists():
            # Ищем любой медиафайл в нашей временной папке
            files = list(download_folder.glob("*.*"))
            if files:
                downloaded_file = files[0]
            else:
                raise FileNotFoundError("Не удалось обнаружить скачанный файл.")

        return downloaded_file


# ==============================================================================
# 4. ОБРАБОТЧИКИ КОМАНД (ХЭНДЛЕРЫ)
# ==============================================================================

@dp.message(CommandStart())
async def handle_start_command(message: Message):
    """
    Обработчик команды /start:
    Приветствует пользователя и кратко объясняет, как пользоваться ботом.
    """
    user_name = message.from_user.first_name if message.from_user else "друг"
    welcome_text = (
        f"👋 Привет, {user_name}! Я бот для скачивания видео из Instagram.\n\n"
        "🚀 **Как пользоваться:**\n"
        "1. Скопируй ссылку на любой **Instagram Reels** или **пост с видео**.\n"
        "2. Просто отправь ссылку сюда сообщением.\n"
        "3. Я скачаю видео и пришлю его тебе файлом без водяных знаков!\n\n"
        "💡 *Пример ссылки:* `https://www.instagram.com/reel/C3b.../`"
    )
    # Отправляем приветствие с поддержкой разметки Markdown
    await message.answer(welcome_text, parse_mode="Markdown")


@dp.message(Command("help"))
async def handle_help_command(message: Message):
    """
    Обработчик команды /help:
    Полезная справка по частым вопросам.
    """
    help_text = (
        "ℹ️ **Справка по боту:**\n\n"
        "• Бот поддерживает ссылки на **Reels**, **посты** и **IGTV**.\n"
        "• Скачивание работает только для **публичных** профилей.\n"
        "• Максимальный размер видео в Telegram — 50 МБ.\n\n"
        "Если ссылка не работает, проверьте, открывается ли видео в браузере без входа в аккаунт."
    )
    await message.answer(help_text, parse_mode="Markdown")


# ==============================================================================
# 5. ГЛАВНЫЙ ОБРАБОТЧИК ССЫЛОК INSTAGRAM
# ==============================================================================

@dp.message(F.text)
async def handle_instagram_link(message: Message):
    """
    Перехватывает текстовые сообщения и ищет в них ссылку на Instagram.
    Если ссылка найдена — скачивает видео, отправляет пользователю и удаляет файл.
    """
    user_text = message.text.strip()

    # Проверяем, содержит ли текст ссылку на Instagram
    match = INSTAGRAM_URL_REGEX.search(user_text)

    # Если ссылки на Instagram нет, вежливо подсказываем формат
    if not match:
        await message.reply(
            "🤔 В этом сообщении нет ссылки на Instagram.\n"
            "Пожалуйста, пришли ссылку в формате: `https://www.instagram.com/reel/...`",
            parse_mode="Markdown"
        )
        return

    # Извлекаем очищенный URL
    instagram_url = match.group(0)

    # Отправляем промежуточное сообщение, чтобы пользователь видел реакцию бота
    status_msg = await message.reply("⏳ Загружаю видео из Instagram... Пожалуйста, подождите.")

    # Показываем анимацию 'загружает видео' в шапке чата Telegram
    await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.UPLOAD_VIDEO)

    # Создаем изолированную временную директорию на диске
    temp_dir = Path(tempfile.mkdtemp(prefix="insta_bot_"))

    try:
        # ВАЖНО ДЛЯ SENIOR PYTHON:
        # yt-dlp является синхронной библиотекой. Если вызвать её напрямую,
        # бот полностью заблокируется для ВСЕХ пользователей на время загрузки!
        # Функция asyncio.to_thread запускает yt-dlp в отдельном системном потоке,
        # оставляя основной цикл событий (event loop) абсолютно свободным!
        video_path = await asyncio.to_thread(
            sync_download_instagram_video,
            instagram_url,
            temp_dir
        )

        # Проверяем размер файла перед отправкой (лимит Telegram Bot API = 50 MB)
        file_size = video_path.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            await status_msg.edit_text(
                "⚠️ Видео слишком большое (>50 МБ). "
                "Telegram Bot API не позволяет ботам отправлять файлы такого размера."
            )
            return

        # Обновляем статус перед отправкой файла
        await status_msg.edit_text("📤 Отправляю видео в чат...")

        # Оборачиваем локальный файл в FSInputFile для потоковой передачи в Telegram
        video_file = FSInputFile(path=video_path)

        # Отправляем видео пользователю
        await message.answer_video(
            video=video_file,
            caption="✨ Приятного просмотра!\n🤖 Скачано с помощью @YourBotName",
            supports_streaming=True  # Позволяет начать просмотр ещё во время загрузки
        )

        # Удаляем сервисное статусное сообщение, чтобы не засорять чат
        await status_msg.delete()

    except yt_dlp.utils.DownloadError as download_err:
        # Ошибка скачивания (приватный аккаунт, видео удалено или блокировка)
        logger.error(f"Ошибка загрузки Instagram: {download_err}")
        await status_msg.edit_text(
            "❌ Не удалось скачать видео.\n"
            "Возможные причины:\n"
            "• Профиль автора приватный (закрытый).\n"
            "• Видео было удалено или ссылка недействительна.\n"
            "• Instagram временно ограничил доступ."
        )

    except Exception as err:
        # Любые другие непредвиденные ошибки
        logger.exception(f"Непредвиденная ошибка: {err}")
        await status_msg.edit_text(
            "⚠️ Произошла непредвиденная ошибка при обработке запроса. "
            "Попробуйте отправить другую ссылку чуть позже."
        )

    finally:
        # КРИТИЧЕСКИ ВАЖНО: блок finally выполняется ВСЕГДА!
        # Удаляем временную папку и файл, чтобы диск на сервере (Render/Koyeb)
        # не переполнился и бот не упал из-за нехватки памяти (Disk Full).
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"Временные файлы очищены: {temp_dir}")


# ==============================================================================
# 6. ТОЧКА ВХОДА И ЗАПУСК БОТА (POLLING)
# ==============================================================================

async def main():
    """
    Главная асинхронная функция:
    Удаляет старые вебхуки (на всякий случай) и запускает опрос Telegram-серверов.
    """
    logger.info("🚀 Запуск Telegram-бота...")

    # Сбрасываем накопившиеся сообщения, пока бот был выключен (drop_pending_updates=True)
    await bot.delete_webhook(drop_pending_updates=True)

    # Запускаем polling (периодический опрос сервера Telegram на наличие новых сообщений)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        # Запуск асинхронного цикла событий Python
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        # Корректное завершение при нажатии Ctrl+C в терминале
        logger.info("🛑 Бот успешно остановлен.")
