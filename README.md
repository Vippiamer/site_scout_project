# SiteScout: Асинхронный веб-сканер

**SiteScout** — модульный асинхронный веб-сканер на Python 3.11+, предназначенный для автоматизированного сбора структуры сайтов, обнаружения документов и скрытых ресурсов, а также анализа локализации контента.

---

## 📖 Описание проекта

- **Цели**:
  - Построить полную карту сайта.
  - Проанализировать HTML, JavaScript, CSS, мета-теги, HTTP-заголовки и SSL.
  - Найти локальные и скрытые файлы (PDF, DOCX, других типов).
  - Обнаружить скрытые пути методом brute-force.
- **Локализация**:
  - Выявляет национальные сегменты сайтов (Япония, Корея, Китай) по поддоменам, URL-паттернам, `Accept-Language` и `hreflang`.
- **Отчёты**:
  - Экспортирует результаты в **JSON** и **HTML** с визуальными таблицами и графиками.

---

## 📂 Структура проекта

```plaintext
site_scout_project/         # Корневой каталог
├── configs/                # Конфигурации (default.yaml)
├── templates/              # Jinja2-шаблоны для HTML-отчёта
├── wordlists/              # Словари для brute-force путей и файлов
├── site_scout/             # Основной пакет
│   ├── config.py           # Pydantic-модель конфигурации
│   ├── logger.py           # Настройка и инициализация логирования
│   ├── engine.py           # Оркестрирование задач (asyncio)
│   ├── utils.py            # Утилиты (URL-обработка, файлы)
│   ├── crawler/            # Модуль краулинга (aiohttp, robots.txt)
│   ├── parser/             # Парсеры: HTML, robots.txt, sitemap.xml
│   ├── doc_finder.py       # Поиск и метаданные документов
│   ├── bruteforce/         # Словарный brute-force скрытых путей
│   ├── localization.py     # Определение национальных сегментов
│   ├── aggregator.py       # Агрегация результатов в ScanReport
│   └── report/             # Рендер JSON/HTML отчетов (Jinja2)
├── tests/                  # Pytest-модули
├── cli.py                  # CLI-точка входа (click)
├── requirements.txt        # Библиотеки проекта
├── pyproject.toml          # Настройки сборки
└── README.md               # Текущая документация
```

---

## 🚀 Установка

1. Клонируйте репозиторий и перейдите в каталог проекта:
   ```bash
   git clone https://github.com/yourusername/site_scout_project.git
   cd site_scout_project
   ```
2. Создайте виртуальное окружение и активируйте его:
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate    # Linux/macOS
   venv\Scripts\activate     # Windows
   ```
3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

---

## 🏃‍♂️ Быстрый старт (CLI)

**Пример конфигурации** в `configs/default.yaml`:
```yaml
base_url: "https://example.com"
max_depth: 3
timeout: 10.0
user_agent: "SiteScoutBot/1.0"
rate_limit: 5.0
wordlists:
  paths: "wordlists/paths.txt"
  files: "wordlists/files.txt"
```

- Сканирование с выводом в консоль:
  ```bash
  python cli.py --config configs/default.yaml
  ```
- Сохранение JSON-отчёта:
  ```bash
  python cli.py -c configs/default.yaml -j reports/output.json
  ```
- Сохранение HTML и JSON:
  ```bash
  python cli.py -c configs/default.yaml -j reports/output.json -h reports/output.html -t templates
  ```

---

## 💡 Пример кода (Python API)

```python
import asyncio
from site_scout.crawler.crawler import AsyncCrawler, PageData
from site_scout.config import ScannerConfig

async def main():
    config = ScannerConfig(
        base_url="https://example.com",
        max_depth=2,
        timeout=5.0,
        user_agent="MyCrawler/1.0",
        rate_limit=5.0,
        wordlists={"paths": "wordlists/paths.txt", "files": "wordlists/files.txt"},
    )

    async with AsyncCrawler(config) as crawler:
        pages = await crawler.crawl()

    for p in pages:
        if isinstance(p.content, str):
            print(f"[Text] {p.url} (len={len(p.content)})")
        else:
            print(f"[Binary] {p.url} (bytes={len(p.content)})")

asyncio.run(main())
```

---

## 🔍 Поддерживаемые типы контента

- **HTML** (`text/html`) — парсится через BeautifulSoup
- **JSON** (`application/json`) — возвращается как строка
- **PDF** (`application/pdf`) — возвращается как байты
- Прочие типы логируются как неподдерживаемые

---

## 🔧 Логирование

Пример вывода:
```
INFO  SiteScout: Старт обхода: https://example.com
INFO  SiteScout: Depth 1: found 10 links
INFO  SiteScout: Depth 1: fetching 10 URLs
INFO  SiteScout: Depth 1: fetched 9/10 pages
INFO  SiteScout: Depth 2: found 20 links
...
INFO  SiteScout: Завершено: 15 страниц за 3.42 c (4.38 стр/с)
```

---

## ✅ Тестирование

Запуск тестов:
```bash
pytest --maxfail=1 --disable-warnings -q
```

---

## 📄 Лицензия

MIT License

