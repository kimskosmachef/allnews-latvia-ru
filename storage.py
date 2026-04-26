import json
import os
import logging

logger = logging.getLogger(__name__)

STORAGE_FILE = "sent_urls.json"


def load_sent_urls() -> set:
    """Загружает список уже отправленных URL из файла"""
    if not os.path.exists(STORAGE_FILE):
        return set()
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Ошибка чтения хранилища: {e}")
        return set()


def save_sent_urls(urls: set):
    """Сохраняет список отправленных URL в файл"""
    try:
        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(urls), f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error(f"Ошибка записи хранилища: {e}")
