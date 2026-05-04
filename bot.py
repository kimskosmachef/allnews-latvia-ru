import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.error import TelegramError, RetryAfter

from config import (
    BOT_TOKEN, CHANNEL_ID,
    CHECK_INTERVAL_MINUTES, NEWS_MAX_AGE_MINUTES,
    NIGHT_MODE_START, NIGHT_MODE_END,
    NIGHT_CHECK_INTERVAL_MINUTES, NIGHT_NEWS_MAX_AGE_MINUTES
)
from scraper import scrape_all_sites
from storage import load_sent_urls, save_sent_urls
from duplicate_checker import is_duplicate, save_to_history
from url_filter import is_filtered

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

RIGA_TZ = ZoneInfo("Europe/Riga")
SEND_DELAY = 3


def get_current_mode() -> dict:
    """
    Определяет текущий режим работы — дневной или ночной.
    Возвращает словарь с интервалом проверки и периодом новостей.
    """
    now_hour = datetime.now(RIGA_TZ).hour
    if NIGHT_MODE_START <= now_hour < NIGHT_MODE_END:
        return {
            "name": "ночной",
            "interval": NIGHT_CHECK_INTERVAL_MINUTES,
            "max_age": NIGHT_NEWS_MAX_AGE_MINUTES,
        }
    return {
        "name": "дневной",
        "interval": CHECK_INTERVAL_MINUTES,
        "max_age": NEWS_MAX_AGE_MINUTES,
    }


async def send_with_retry(bot: Bot, chat_id: str, text: str, retries: int = 3) -> bool:
    """Отправляет сообщение с повтором при ошибке Flood control"""
    for attempt in range(retries):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=False
            )
            return True

        except RetryAfter as e:
            wait = e.retry_after + 2
            logger.warning(f"Flood control, жду {wait} секунд...")
            await asyncio.sleep(wait)

        except TelegramError as e:
            logger.error(f"Ошибка Telegram (попытка {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(5)
            else:
                return False

    return False


def filter_and_sort(news_items: list[dict], sent_urls: set, max_age_minutes: int) -> list[dict]:
    """
    Фильтрует новости — только свежие за последние max_age_minutes минут.
    Сортирует от старой к новой.
    """
    now = datetime.now(RIGA_TZ).replace(tzinfo=None)
    cutoff = now - timedelta(minutes=max_age_minutes)

    fresh = []
    for item in news_items:
        if item["url"] in sent_urls:
            continue

        pub_time = item.get("published_at")

        if pub_time is None:
            # Время неизвестно — пропускаем
            sent_urls.add(item["url"])
            continue
        elif pub_time >= cutoff:
            fresh.append(item)
        else:
            # Новость старше периода — помечаем чтобы не проверять снова
            sent_urls.add(item["url"])

    fresh.sort(key=lambda x: x["published_at"])
    return fresh


async def check_and_send_news(bot: Bot, scheduler: AsyncIOScheduler):
    mode = get_current_mode()
    logger.info(f"Проверяю новости... [{mode['name']} режим]")

    sent_urls = load_sent_urls()
    all_items = scrape_all_sites()
    items_to_send = filter_and_sort(all_items, sent_urls, mode["max_age"])

    logger.info(
        f"Всего найдено: {len(all_items)} | "
        f"Свежих для публикации: {len(items_to_send)}"
    )

    new_count = 0
    duplicate_count = 0
    error_count = 0

    for item in items_to_send:
        paragraph = item.get("first_paragraph", "")

        # Проверяем фильтры URL и рубрик
        logger.info(f"Проверяю фильтр: source={item.get('source')}, sections={item.get('sections', [])}") #логгер для отладки
        if is_filtered(item["url"], item["title"], item.get("source", ""), item.get("sections", [])):
            sent_urls.add(item["url"])
            continue

        if is_duplicate(item["title"], paragraph):
            logger.info(f"Дубль, пропускаю: {item['title']}")
            duplicate_count += 1
            sent_urls.add(item["url"])
            continue

        pub_time = item.get("published_at")
        time_str = pub_time.strftime("%H:%M") if pub_time else ""
        source_str = item.get("source", "")

        header = f"🕐 {time_str} | {source_str}" if time_str else f"📡 {source_str}"
        message = f"{header}\n\n📰 <b>{item['title']}</b>\n\n🔗 {item['url']}"

        success = await send_with_retry(bot, CHANNEL_ID, message)

        if success:
            sent_urls.add(item["url"])
            save_to_history(item["title"], item["url"], paragraph)
            new_count += 1
            logger.info(f"Опубликовано [{time_str}] [{source_str}]: {item['title']}")
        else:
            error_count += 1

        await asyncio.sleep(SEND_DELAY)

    save_sent_urls(sent_urls)
    logger.info(
        f"Готово — опубликовано: {new_count} | "
        f"дублей пропущено: {duplicate_count} | "
        f"ошибок: {error_count}"
    )

    # Перепланируем следующий запуск с актуальным интервалом
    next_mode = get_current_mode()
    scheduler.reschedule_job(
        "news_check",
        trigger="interval",
        minutes=next_mode["interval"]
    )
    logger.info(
        f"Следующая проверка через {next_mode['interval']} мин. "
        f"[{next_mode['name']} режим]"
    )


async def main():
    logger.info("Запускаю бота...")

    bot = Bot(token=BOT_TOKEN)

    try:
        me = await bot.get_me()
        logger.info(f"Бот подключён: @{me.username}")
    except TelegramError as e:
        logger.error(f"Не удалось подключиться к Telegram: {e}")
        return

    # Запускаем с интервалом текущего режима
    mode = get_current_mode()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_send_news,
        trigger="interval",
        minutes=mode["interval"],
        args=[bot, scheduler],
        id="news_check"
    )
    scheduler.start()
    logger.info(
        f"Планировщик запущен. [{mode['name']} режим] "
        f"Проверка каждые {mode['interval']} мин. | "
        f"Период новостей: {mode['max_age']} мин."
    )

    await check_and_send_news(bot, scheduler)

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка бота...")
        scheduler.shutdown()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
