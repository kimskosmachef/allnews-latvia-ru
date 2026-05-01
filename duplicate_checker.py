import json
import logging
import os
from datetime import datetime, timedelta

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import DUPLICATE_WINDOW_HOURS, SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)

HISTORY_FILE = "news_history.json"


# ──────────────────────────────────────────────
# История новостей
# ──────────────────────────────────────────────

def load_history() -> list[dict]:
    """Загружает историю новостей за последние N часов"""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cutoff = datetime.now() - timedelta(hours=DUPLICATE_WINDOW_HOURS)
        return [
            item for item in data
            if datetime.fromisoformat(item["published_at"]) > cutoff
        ]
    except Exception as e:
        logger.error(f"Ошибка чтения истории: {e}")
        return []


def save_to_history(title: str, url: str, first_paragraph: str = ""):
    """Добавляет опубликованную новость в историю"""
    history = load_history()
    history.append({
        "title": title,
        "url": url,
        "first_paragraph": first_paragraph,
        "published_at": datetime.now().isoformat()
    })
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка записи истории: {e}")


# ──────────────────────────────────────────────
# Формирование текста для сравнения
# ──────────────────────────────────────────────

def build_text(title: str, paragraph: str) -> str:
    """
    Объединяет заголовок и первый абзац.
    Заголовок повторяем дважды — чтобы он имел больший вес.
    """
    return f"{title} {title} {paragraph}".strip()


# ──────────────────────────────────────────────
# Проверка через TF-IDF
# ──────────────────────────────────────────────

def is_duplicate(title: str, first_paragraph: str = "") -> bool:
    """
    Проверяет, является ли новость дублём через TF-IDF.

    Логика:
      similarity < threshold  → не дубль, публикуем
      similarity >= threshold → дубль, пропускаем
    """
    history = load_history()
    if not history:
        return False

    new_text = build_text(title, first_paragraph)
    history_texts = [
        build_text(item["title"], item.get("first_paragraph", ""))
        for item in history
    ]

    vectorizer = TfidfVectorizer()
    try:
        tfidf_matrix = vectorizer.fit_transform(history_texts + [new_text])
        new_vec = tfidf_matrix[-1]
        existing_vecs = tfidf_matrix[:-1]
        similarities = cosine_similarity(new_vec, existing_vecs)[0]
        max_similarity = float(similarities.max())
        max_idx = similarities.argmax()

        logger.info(
            f"TF-IDF сходство: {max_similarity:.2f} | "
            f"'{title}' vs '{history[max_idx]['title']}'"
        )

        if max_similarity >= SIMILARITY_THRESHOLD:
            logger.info(
                f"Дубль обнаружен (сходство: {max_similarity:.2f}):\n"
                f"  Новая:     '{title[:80]}'\n"
                f"  Совпала с: '{history[max_idx]['title'][:80]}'"
            )
            return True

        return False

    except Exception as e:
        logger.error(f"Ошибка TF-IDF: {e}")
        return False  # при ошибке не блокируем публикацию
