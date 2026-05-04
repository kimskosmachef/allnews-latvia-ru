import os
from dotenv import load_dotenv

# Загружаем .env файл если он есть (локальная разработка)
# На Railway .env не нужен — там переменные задаются через Variables
load_dotenv()

# ================================
# СЕКРЕТНЫЕ НАСТРОЙКИ
# Локально берутся из .env файла
# На Railway берутся из Variables
# ================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "")

# ================================
# НАСТРОЙКИ МОНИТОРИНГА
# ================================

# Дневной режим (07:00 — 01:00)
CHECK_INTERVAL_MINUTES = 10        # как часто проверять (минуты)
NEWS_MAX_AGE_MINUTES = 25          # за какой период брать новости (минуты)

# Ночной режим (01:00 — 07:00)
NIGHT_MODE_START = 1               # час начала ночного режима (по латвийскому времени)
NIGHT_MODE_END = 7                 # час конца ночного режима (по латвийскому времени)
NIGHT_CHECK_INTERVAL_MINUTES = 60  # как часто проверять ночью (минуты)
NIGHT_NEWS_MAX_AGE_MINUTES = 75    # за какой период брать новости ночью (минуты)

# ================================
# НАСТРОЙКИ ПРОВЕРКИ ДУБЛЕЙ
# ================================

# Метод проверки дублей:
#   "tfidf"                — быстро, без доп. зависимостей, хуже понимает смысл
#   "sentence_transformers" — медленнее, точнее, понимает перефразированные заголовки
DUPLICATE_METHOD = "sentence_transformers"

# За сколько последних часов проверять дубли
DUPLICATE_WINDOW_HOURS = 6

# Порог сходства от 0 до 1:
# Для TF-IDF рекомендуется: 0.6
# Для sentence-transformers рекомендуется: 0.75
# (sentence-transformers даёт более высокие значения для похожих текстов)
SIMILARITY_THRESHOLD = 0.55

# ================================
# САЙТЫ ДЛЯ ПАРСИНГА
# ================================
SITES = [
    {
        "name": "BB.lv",
        "type": "scrape",
        "url": "https://bb.lv/line",
        "article_selector": "a[href*='/statja/']",
        "base_url": "https://bb.lv",
        "fetch_paragraph": False,
    },
    {
        "name": "Mixnews",
        "type": "scrape",
        "url": "https://mixnews.lv/novosti/",
        "article_selector": "h2 a[href*='2026']",  # ← только ссылки на статьи с годом в URL
        "base_url": "https://mixnews.lv",
        "fetch_paragraph": True,
        "time_in_title": True,
        "stop_on_date_header": True,  # ← останавливаемся на разделителе "24 Апрель"
    },
    {
        "name": "RUS TVNET",
        "type": "scrape",
        "url": "https://rus.tvnet.lv/latest",
        "article_selector": "a[href*='/8']",
        "base_url": "https://rus.tvnet.lv",
    },
    {
        "name": "Rus Jauns",
        "type": "scrape",
        "url": "https://rus.jauns.lv/recent",
        "article_selector": "a[href*='/article/']",
        "base_url": "https://rus.jauns.lv",
        "fetch_paragraph": False,  # сайт блокирует запросы к статьям
    },
    {
        "name": "Rus LSM",
        "type": "rss",
        "url": "https://rus.lsm.lv/rss/",
        "base_url": "https://rus.lsm.lv",
        "tz_offset": 2,  # BST = UTC+1, по-латвийски +2 часа
    },
    {
        "name": "Rus Delfi",
        "type": "rss",
        "url": "https://rus.delfi.lv/rss/index.xml",
        "base_url": "https://rus.delfi.lv",
        # tz_offset не указан — используем Europe/Riga по умолчанию
    },
    {
        "name": "Rus Delfi Бизнес",
        "type": "rss",
        "url": "https://rus.delfi.lv/biznes/rss/index.xml",
        "base_url": "https://rus.delfi.lv",
    },
    {
        "name": "Rus Delfi Life",
        "type": "rss",
        "url": "https://rus.delfi.lv/life/rss/index.xml",
        "base_url": "https://rus.delfi.lv",
    },
    {
        "name": "Rus Delfi Спорт",
        "type": "rss",
        "url": "https://rus.delfi.lv/sport/rss/index.xml",
        "base_url": "https://rus.delfi.lv",
    },
#    {
#        "name": "Rus Delfi Дом и сад",
#        "type": "rss",
#        "url": "https://rus.delfi.lv/domsad/rss/index.xml",
#        "base_url": "https://rus.delfi.lv",
#    },    
#    {
#        "name": "Rus Delfi Тургид",
#        "type": "rss",
#        "url": "https://rus.delfi.lv/turgid/rss/index.xml",
#        "base_url": "https://rus.delfi.lv",
#    },
    {
        "name": "Rus Delfi Прогноз погоды",
        "type": "rss",
        "url": "https://rus.delfi.lv/prognoz-pogody/rss/index.xml",
        "base_url": "https://rus.delfi.lv",
    },
    # Добавляй новые сайты по образцу:
    # Для скрапинга:
    # {
    #     "name": "Название",
    #     "type": "scrape",
    #     "url": "https://example.com/news/",
    #     "article_selector": "CSS-селектор ссылок",
    #     "base_url": "https://example.com",
    # },
    # Для RSS:
    # {
    #     "name": "Название",
    #     "type": "rss",
    #     "url": "https://example.com/rss.xml",
    #     "base_url": "https://example.com",
    # },
]

# ================================
# НАСТРОЙКИ ФИЛЬТРАЦИИ ПО URL С ОТДЕЛЬНЫХ САЙТОВ
# ================================

URL_FILTERS_ENABLED = True   # включить/выключить одной строкой, для отключения - URL_FILTERS_ENABLED = False

# Список фильтров для каждого источника.
# Если любая из строк найдена в URL — новость не публикуется.
# Ключ — название источника как в SITES["name"]
URL_FILTERS = {
    "BB.lv": [
        "/statja/v-mire/",  # международные новости — не публикуем
        "/statja/lifenews/",    # хрень не публикуем
        "/statja/v-mire-zhivotnyh/", # про животных не публикуем
        "/statja/ljublju/",  # про моду не публикуем
        "/statja/tehno/", #типа науку не публикуем
        "/statja/eda-i-recepty/", #еду не публикуем
        "/statja/dom-i-sad/", #дом и сад пропускаем
    ],
    "Mixnews": [
        "mixnews.lv/v-mire/", # международные новости - не публикуем
        "https://mixnews.lv/nauka/",    #науку пропускаем
    ],
    "Rus Jauns": [
        "/article/lifestyle/", # лайфстайл не публикуем
    ],
    "Rus Delfi": [
        "/v-mire/", # международку не публикуем
    ],
    "Rus LSM":  [
        "statja/novosti/mir/", # международку не публикуем
    ]
}

# Фильтрация по рубрикам через хлебные крошки в теле статьи
# Бот заходит на страницу статьи и проверяет наличие запрещённых рубрик
# Работает совместно с fetch_paragraph — не добавляет лишних запросов
# Ключ — название источника, значение — список строк-идентификаторов рубрик
SECTION_FILTERS = {
    "RUS TVNET": [
        # "/section/4368",  # За рубежом
        # Добавляй другие рубрики по образцу:
        # "/section/4371",  # Спорт
    ],
}