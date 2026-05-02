import logging
import requests
from bs4 import BeautifulSoup
from config import URL_FILTERS_ENABLED, URL_FILTERS, SECTION_FILTERS

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Кэш заголовков рубрик — обновляется раз в цикл
_section_cache: dict[str, set] = {}


def fetch_section_titles(section_url: str) -> set:
    """
    Загружает заголовки новостей из рубрики tvnet.
    Останавливается на блоке 'Читаемые' — его новости не берём.
    """
    try:
        response = requests.get(section_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        titles = set()
        for tag in soup.find_all(["h2", "h3"]):
            # Останавливаемся на блоке "Читаемые"
            if tag.name == "h3" and "Читаемые" in tag.get_text():
                break
            if tag.name == "h2":
                title = tag.get_text(strip=True)
                if title:
                    titles.add(title.lower())

        logger.info(f"Рубрика {section_url}: загружено {len(titles)} заголовков")
        return titles

    except Exception as e:
        logger.error(f"Ошибка загрузки рубрики {section_url}: {e}")
        return set()


def refresh_section_cache():
    """Обновляет кэш заголовков всех рубрик из SECTION_FILTERS"""
    global _section_cache
    if not URL_FILTERS_ENABLED:
        return
    for source, sections in SECTION_FILTERS.items():
        for section_url in sections:
            _section_cache[section_url] = fetch_section_titles(section_url)


def is_in_section(title: str, source: str) -> bool:
    """
    Проверяет есть ли заголовок новости в одной из запрещённых рубрик.
    Возвращает True если новость нужно пропустить.
    """
    if not URL_FILTERS_ENABLED:
        return False

    sections = SECTION_FILTERS.get(source, [])
    title_lower = title.lower()

    for section_url in sections:
        section_titles = _section_cache.get(section_url, set())
        if title_lower in section_titles:
            logger.info(
                f"Фильтр рубрики сработал: '{title[:80]}'\n"
                f"  Источник: {source} | Рубрика: {section_url} — новость пропущена"
            )
            return True

    return False


def is_filtered_by_url(url: str, source: str) -> bool:
    """
    Проверяет URL на наличие запрещённых строк.
    Возвращает True если новость нужно пропустить.
    """
    if not URL_FILTERS_ENABLED:
        return False

    filters = URL_FILTERS.get(source, [])
    for pattern in filters:
        if pattern in url:
            logger.info(
                f"Фильтр URL сработал: '{pattern}' найден в {url}\n"
                f"  Источник: {source} — новость пропущена"
            )
            return True

    return False


def is_filtered(url: str, title: str, source: str) -> bool:
    """
    Главная функция фильтрации — проверяет оба фильтра:
    1. По URL (для bb.lv и других)
    2. По рубрике (для tvnet)
    """
    if is_filtered_by_url(url, source):
        return True
    if is_in_section(title, source):
        return True
    return False
