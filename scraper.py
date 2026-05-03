import logging
import re
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

RIGA_TZ = ZoneInfo("Europe/Riga")

import feedparser
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from config import SITES, NEWS_MAX_AGE_MINUTES

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# ──────────────────────────────────────────────
# Парсинг времени публикации
# ──────────────────────────────────────────────

def parse_pub_time(time_str: str) -> datetime | None:
    """
    Универсальный парсер времени публикации.
    Поддерживает форматы:
      "Сегодня, 21:30"   (tvnet)
      "Сегодня 21:30"    (jauns)
      "Вчера, 10:00"     (tvnet)
      "Вчера 10:00"      (jauns)
      "15 минут назад"   (bb.lv)
      "41 минуту назад"  (bb.lv)
      "1 час назад"      (bb.lv)
      "2 часа назад"     (bb.lv)
    """
    # Всегда используем латвийское время для корректного сравнения
    now = datetime.now(RIGA_TZ).replace(tzinfo=None)
    time_str = time_str.strip()

    # "Сегодня, HH:MM" или "Сегодня HH:MM"
    match = re.match(r"Сегодня[,\s]\s*(\d{1,2}):(\d{2})", time_str)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        return now.replace(hour=h, minute=m, second=0, microsecond=0)

    # "Вчера, HH:MM" или "Вчера HH:MM"
    match = re.match(r"Вчера[,\s]\s*(\d{1,2}):(\d{2})", time_str)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        yesterday = now - timedelta(days=1)
        return yesterday.replace(hour=h, minute=m, second=0, microsecond=0)

    # "X секунд(у) назад" (bb.lv)
    match = re.match(r"(\d+)\s+сек", time_str)
    if match:
        seconds = int(match.group(1))
        return now - timedelta(seconds=seconds)

    # "X минут(у/ы) назад" (bb.lv)
    match = re.match(r"(\d+)\s+мин", time_str)
    if match:
        minutes = int(match.group(1))
        return now - timedelta(minutes=minutes)

    # "X час(а/ов) назад" (bb.lv)
    match = re.match(r"(\d+)\s+час", time_str)
    if match:
        hours = int(match.group(1))
        # Всегда возвращаем реальное время — filter_and_sort сам отсеет старые
        return now - timedelta(hours=hours)

    # "HH:MM" — время в начале заголовка (mixnews.lv), пробел необязателен
    match = re.match(r"^(\d{1,2}):(\d{2})\s*", time_str)
    if match:
        h, m = int(match.group(1)), int(match.group(2))
        return now.replace(hour=h, minute=m, second=0, microsecond=0)

    # "DD.MM.YYYY" — дата без времени (jauns.lv для старых новостей)
    # Если дата не сегодня — возвращаем вчерашнюю полночь чтобы новость была отброшена
    match = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", time_str)
    if match:
        d, m, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
        pub_date = now.replace(year=y, month=m, day=d, hour=0, minute=0, second=0, microsecond=0)
        if pub_date.date() < now.date():
            # Новость не сегодняшняя — вернём старую дату, filter_and_sort отсеет
            return pub_date
        # Сегодняшняя новость без точного времени — считаем что опубликована в начале дня
        return pub_date

    return None


def split_mixnews_title(raw: str) -> tuple[str, datetime | None]:
    """
    Разделяет строку вида "19:00 Заголовок" или "19:00Заголовок" на время и заголовок.
    Если полученное время в будущем — значит это вчерашняя новость.
    Возвращает (заголовок, published_at).
    """
    match = re.match(r"^(\d{1,2}:\d{2})\s*(.+)$", raw.strip())
    if match:
        time_str = match.group(1)
        title = match.group(2).strip()
        published_at = parse_pub_time(time_str)
        # Если время в будущем — это вчерашняя новость
        if published_at:
            now = datetime.now(RIGA_TZ).replace(tzinfo=None)
            if published_at > now:
                published_at = published_at - timedelta(days=1)
        return title, published_at
    return raw.strip(), None


# ──────────────────────────────────────────────
# Извлечение заголовка
# ──────────────────────────────────────────────

def extract_title(link) -> str:
    """
    Универсальное извлечение заголовка из тега <a>.
    Пробует несколько способов подходящих для разных сайтов.
    """
    title = ""

    # 1. Ищем h2/h3 внутри самой ссылки (tvnet, jauns)
    h_tag = link.find("h2") or link.find("h3")
    if h_tag:
        title = h_tag.get_text(strip=True)
        if title:
            return title

    # 2. Берём из атрибута alt картинки (bb.lv)
    # Формат: "Изображение к статье: Заголовок новости"
    img = link.find("img")
    if img:
        alt = img.get("alt", "").strip()
        prefix = "Изображение к статье: "
        if alt.startswith(prefix):
            title = alt[len(prefix):].strip()
        elif alt and not alt.startswith("http"):
            title = alt
        if title:
            return title

    # 3. Берём текст самой ссылки (если не пустой)
    title = link.get_text(strip=True)
    if title:
        return title

    # 4. Ищем h-тег в родительском блоке
    parent_block = link.parent
    for _ in range(4):
        if parent_block is None:
            break
        h_tag = parent_block.find(["h2", "h3", "h4"])
        if h_tag:
            title = h_tag.get_text(strip=True)
            if title:
                return title
        parent_block = parent_block.parent

    return "Без заголовка"


# ──────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────

def fetch_article_data(url: str) -> tuple[str, list[str]]:
    """
    Заходит на страницу статьи и возвращает:
    - первый абзац текста
    - список рубрик из хлебных крошек (breadcrumbs) в формате ['/section/4368', ...]
    """
    paragraph = ""
    sections = []
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Извлекаем рубрики из хлебных крошек
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/section/" in href:
                # Берём только путь без домена
                path = "/" + href.split("/", 3)[-1] if href.startswith("http") else href
                if path not in sections:
                    sections.append(path)

        # Извлекаем первый абзац
        candidates = [
            "article p", ".article-body p", ".article__body p",
            ".content p", ".text p", ".entry-content p", "main p", "p",
        ]
        for selector in candidates:
            for p in soup.select(selector):
                text = p.get_text(strip=True)
                if len(text) > 60:
                    paragraph = text[:500]
                    break
            if paragraph:
                break

    except Exception as e:
        logger.warning(f"Не удалось получить данные для {url}: {e}")

    return paragraph, sections


def fetch_first_paragraph(url: str) -> str:
    """Обратная совместимость — возвращает только абзац"""
    paragraph, _ = fetch_article_data(url)
    return paragraph


# ──────────────────────────────────────────────
# RSS
# ──────────────────────────────────────────────

def scrape_rss(site: dict) -> list[dict]:
    """Читает RSS-ленту, возвращает новости с временем публикации"""
    results = []
    try:
        feed = feedparser.parse(site["url"])
        for entry in feed.entries:
            url = entry.get("link", "").strip()
            title = entry.get("title", "Без заголовка").strip()

            # Время публикации из RSS
            published_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                utc_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                if "tz_offset" in site:
                    # Явное смещение — для источников где часовой пояс в фиде указан неверно
                    published_at = (utc_dt + timedelta(hours=site["tz_offset"])).replace(tzinfo=None)
                else:
                    # По умолчанию конвертируем через Europe/Riga (учитывает летнее/зимнее время)
                    published_at = utc_dt.astimezone(RIGA_TZ).replace(tzinfo=None)

            # Первый абзац из summary
            summary = entry.get("summary", "")
            if summary:
                summary = BeautifulSoup(summary, "html.parser").get_text(strip=True)[:500]

            if url and url.startswith("http"):
                results.append({
                    "title": title,
                    "url": url,
                    "first_paragraph": summary,
                    "published_at": published_at,
                    "source": site["name"],
                })

        logger.info(f"[{site['name']}] RSS: получено {len(results)} новостей")

    except Exception as e:
        logger.error(f"[{site['name']}] Ошибка чтения RSS: {e}")

    return results


# ──────────────────────────────────────────────
# Скрапинг
# ──────────────────────────────────────────────

def scrape_site(site: dict) -> list[dict]:
    """Парсит сайт, возвращает новости с временем публикации"""
    results = []
    try:
        response = requests.get(site["url"], headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        seen_urls = set()

        # Для сайтов где дни разделены заголовком типа "24 Апрель" (mixnews)
        # обходим все h2 по порядку и останавливаемся на разделителе
        if site.get("stop_on_date_header"):
            all_h2 = soup.find_all("h2")
            links = []
            for h2 in all_h2:
                a = h2.find("a")
                if a:
                    links.append(a)
                else:
                    # h2 без ссылки — это разделитель дат, дальше вчерашние новости
                    h2_text = h2.get_text(strip=True)
                    if re.search(r"\d+\s+[А-Яа-я]+", h2_text):
                        logger.info(f"[{site['name']}] Стоп на разделителе: '{h2_text}'")
                        break
        else:
            links = soup.select(site["article_selector"])

        for link in links:
            href = link.get("href", "").strip()
            if not href:
                continue

            full_url = urljoin(site["base_url"], href)
            if not full_url.startswith("http"):
                continue
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Заголовок и время публикации
            raw_title = extract_title(link)

            # Для mixnews.lv время встроено в заголовок: "19:00 Заголовок"
            if site.get("time_in_title"):
                title, published_at = split_mixnews_title(raw_title)
            else:
                title = raw_title
                # Время публикации — поднимаемся по DOM до 6 уровней вверх
                published_at = None
                parent = link.parent
                for _ in range(6):
                    if parent is None:
                        break
                    time_tag = parent.find(string=re.compile(r"Сегодня|Вчера|назад|\d{2}\.\d{2}\.\d{4}"))
                    if time_tag:
                        published_at = parse_pub_time(str(time_tag).strip())
                        if published_at:
                            break
                    parent = parent.parent

            results.append({
                "title": title,
                "url": full_url,
                "first_paragraph": "",
                "sections": [],
                "published_at": published_at,
                "source": site["name"],
            })

        logger.info(f"[{site['name']}] Найдено {len(results)} ссылок")

    except requests.RequestException as e:
        logger.error(f"[{site['name']}] Ошибка запроса: {e}")
    except Exception as e:
        logger.error(f"[{site['name']}] Неожиданная ошибка: {e}")

    # Заходим на каждую статью за первым абзацем (если сайт это разрешает)
    if site.get("fetch_paragraph", True):
        for item in results:
            item["first_paragraph"] = fetch_first_paragraph(item["url"])
            time.sleep(0.5)
    else:
        logger.info(f"[{site['name']}] Пропускаю загрузку абзацев (fetch_paragraph=False)")
        for item in results:
            item["first_paragraph"] = ""

    return results


# ──────────────────────────────────────────────
# Главная функция
# ──────────────────────────────────────────────

def scrape_all_sites() -> list[dict]:
    """Парсит все сайты, возвращает список новостей с временем публикации"""
    all_news = []
    for site in SITES:
        if site.get("type") == "rss":
            items = scrape_rss(site)
        else:
            items = scrape_site(site)
        all_news.extend(items)
    return all_news
