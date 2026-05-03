import logging
from config import URL_FILTERS_ENABLED, URL_FILTERS, SECTION_FILTERS

logger = logging.getLogger(__name__)


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


def is_filtered_by_section(sections: list[str], source: str) -> bool:
    """
    Проверяет рубрики статьи (из хлебных крошек) на наличие запрещённых.
    sections — список путей вида ['/section/4368', '/section/4364']
    Возвращает True если новость нужно пропустить.
    """
    if not URL_FILTERS_ENABLED:
        return False

    forbidden = SECTION_FILTERS.get(source, [])
    
    
    for section in sections:
        for pattern in forbidden:
            if pattern in section:
                logger.info(
                    f"Фильтр рубрики сработал: '{pattern}' найден в хлебных крошках\n"
                    f"  Источник: {source} | Рубрика: {section} — новость пропущена"
                )
                return True

    return False


def is_filtered(url: str, title: str, source: str, sections: list[str] = []) -> bool:
    """
    Главная функция фильтрации — проверяет оба фильтра:
    1. По URL (для bb.lv и других)
    2. По рубрике из хлебных крошек (для tvnet)
    """
    if is_filtered_by_url(url, source):
        return True
    if is_filtered_by_section(sections, source):
        return True
    return False
