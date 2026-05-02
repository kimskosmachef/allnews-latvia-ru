import logging
from config import URL_FILTERS_ENABLED, URL_FILTERS

logger = logging.getLogger(__name__)


def is_filtered(url: str, source: str) -> bool:
    """
    Проверяет URL на наличие запрещённых строк.
    Возвращает True если новость нужно пропустить.

    Фильтры задаются в config.py в URL_FILTERS —
    словарь где ключ это название источника,
    значение — список строк которые нельзя публиковать.
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
