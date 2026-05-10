import json
import logging
import os
from datetime import datetime, timedelta

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config import DUPLICATE_WINDOW_HOURS, SIMILARITY_THRESHOLD, DUPLICATE_METHOD

logger = logging.getLogger(__name__)

HISTORY_FILE = "news_history.json"

# ──────────────────────────────────────────────
# Sentence-transformers (загружается один раз)
# ──────────────────────────────────────────────

_st_model = None

def get_st_model():
    """Загружает модель sentence-transformers один раз и кэширует её"""
    global _st_model
    if _st_model is None:
        logger.info("Загружаю модель sentence-transformers (первый запуск может занять 1-2 минуты)...")
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")
        logger.info("Модель sentence-transformers загружена успешно")
    return _st_model


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


def save_to_history(title: str, url: str, first_paragraph: str = "",
                    source: str = "", message_id: int = None,
                    published_time: str = ""):
    """Добавляет опубликованную новость в историю"""
    history = load_history()
    history.append({
        "title": title,
        "url": url,
        "first_paragraph": first_paragraph,
        "source": source,
        "message_id": message_id,
        "published_time": published_time,
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
    """Заголовок повторяется дважды для большего веса"""
    return f"{title} {title} {paragraph}".strip()


# ──────────────────────────────────────────────
# Метод 1: TF-IDF
# ──────────────────────────────────────────────

def check_tfidf(title: str, first_paragraph: str, history: list[dict]) -> tuple[bool, float, dict]:
    """
    Проверка дублей через TF-IDF.
    Возвращает (is_duplicate, max_similarity, most_similar_item)
    """
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
        max_idx = similarities.argmax()
        max_similarity = float(similarities[max_idx])
        most_similar_item = history[max_idx]
        return max_similarity >= SIMILARITY_THRESHOLD, max_similarity, most_similar_item
    except Exception as e:
        logger.error(f"Ошибка TF-IDF: {e}")
        return False, 0.0, {}


# ──────────────────────────────────────────────
# Метод 2: Sentence-Transformers
# ──────────────────────────────────────────────

def check_sentence_transformers(title: str, first_paragraph: str, history: list[dict]) -> tuple[bool, float, dict]:
    """
    Проверка дублей через sentence-transformers (семантическое сходство).
    Возвращает (is_duplicate, max_similarity, most_similar_item)
    """
    try:
        model = get_st_model()

        new_text = build_text(title, first_paragraph)
        history_texts = [
            build_text(item["title"], item.get("first_paragraph", ""))
            for item in history
        ]

        # Кодируем все тексты в векторы
        all_texts = history_texts + [new_text]
        embeddings = model.encode(all_texts, convert_to_tensor=False)

        new_embedding = embeddings[-1].reshape(1, -1)
        history_embeddings = embeddings[:-1]

        similarities = cosine_similarity(new_embedding, history_embeddings)[0]
        max_idx = similarities.argmax()
        max_similarity = float(similarities[max_idx])
        most_similar_item = history[max_idx]

        return max_similarity >= SIMILARITY_THRESHOLD, max_similarity, most_similar_item

    except Exception as e:
        logger.error(f"Ошибка sentence-transformers: {e}")
        return False, 0.0, {}


# ──────────────────────────────────────────────
# Главная функция проверки
# ──────────────────────────────────────────────

def is_duplicate(title: str, first_paragraph: str = "") -> dict:
    """
    Проверяет является ли новость дублём.
    Метод определяется параметром DUPLICATE_METHOD в config.py:
      "tfidf"               — TF-IDF (быстро, без доп. зависимостей)
      "sentence_transformers" — семантическое сходство (точнее, понимает смысл)

    Возвращает словарь:
      {
        "is_duplicate": bool,
        "similarity": float,
        "most_similar_title": str,
        "most_similar_source": str,
        "most_similar_time": str,
        "most_similar_message_id": int | None,
      }
    """
    history = load_history()
    if not history:
        return {
            "is_duplicate": False,
            "similarity": 0.0,
            "most_similar_title": "",
            "most_similar_source": "",
            "most_similar_time": "",
            "most_similar_message_id": None,
        }

    if DUPLICATE_METHOD == "sentence_transformers":
        is_dup, similarity, most_similar_item = check_sentence_transformers(
            title, first_paragraph, history
        )
        method_label = "Sentence-Transformers"
    else:
        is_dup, similarity, most_similar_item = check_tfidf(
            title, first_paragraph, history
        )
        method_label = "TF-IDF"

    most_similar_title = most_similar_item.get("title", "")

    logger.info(
        f"{method_label} сходство: {similarity:.2f} | "
        f"'{title[:60]}' vs '{most_similar_title[:60]}'"
    )

    if is_dup:
        logger.info(
            f"Дубль обнаружен [{method_label}] "
            f"(сходство: {similarity:.2f}, порог: {SIMILARITY_THRESHOLD}):\n"
            f"  Новая:     '{title[:80]}'\n"
            f"  Совпала с: '{most_similar_title[:80]}'"
        )

    return {
        "is_duplicate": is_dup,
        "similarity": similarity,
        "most_similar_title": most_similar_title,
        "most_similar_source": most_similar_item.get("source", ""),
        "most_similar_time": most_similar_item.get("published_time", ""),
        "most_similar_message_id": most_similar_item.get("message_id"),
    }
