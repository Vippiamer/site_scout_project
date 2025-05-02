# SiteScout: Асинхронный веб-сканер

**SiteScout** — модульный асинхронный веб-сканер на Python 3.11+, предназначенный для автоматизированного сбора структуры сайтов, обнаружения документов и скрытых ресурсов, а также анализа локализации контента.

---

## 📖 Описание проекта

**Цели проекта:**

* Построить полную карту сайта.
* Проанализировать HTML, JavaScript, CSS, мета-теги, HTTP-заголовки и SSL/TLS.
* Обнаружить локальные и скрытые файлы (PDF, DOCX и другие).
* Найти скрытые пути методом brute-force.
* Выявить национальные сегменты сайтов (Япония, Корея, Китай) по поддоменам, URL-паттернам, `Accept-Language` и `hreflang`.
* Экспортировать результаты в **JSON** и **HTML** с визуальными таблицами и графиками.

---

## 🚀 Быстрый старт

1. Клонируйте репозиторий:

   ```bash
   git clone https://github.com/Vippiamer/site_scout_project.git
   cd site_scout_project
   ```
2. Создайте и активируйте виртуальное окружение:

   ````bash
   python -m venv venv
   # Linux/macOS
   source venv/bin/activate
   # Windows (PowerShell)
   .\venv\Scripts\Activate.ps1
   # Windows (CMD)
   venv\Scripts\activate.bat
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ````
3. Установите зависимости:

   ```bash
   pip install -r requirements.txt
   ```
4. Установите pre-commit хуки:

   ```bash
   pre-commit install
   ```
5. Запустите сканирование:

   ```bash
   python cli.py --url https://example.com --depth 1
   ```

---

## 📂 Структура проекта

```plaintext
site_scout_project/         # Корневой каталог
├── configs/                # Конфигурационные файлы (например, default.yaml)
├── templates/              # Jinja2-шаблоны для HTML-отчетов
├── wordlists/              # Словари для brute-force путей и файлов
├── site_scout/             # Основной пакет
│   ├── config.py           # Pydantic-модель конфигурации (ConfigDict)
│   ├── logger.py           # Настройка и инициализация логирования
│   ├── engine.py           # Оркестрирование задач (asyncio)
│   ├── utils.py            # Утилиты (URL-обработка, файловые операции)
│   ├── crawler/            # Модуль краулинга (aiohttp, robots.txt)
│   ├── parser/             # Парсеры: HTML, robots.txt, sitemap.xml
│   ├── doc_finder.py       # Поиск документов и метаданные
│   ├── bruteforce/         # Словарный brute-force скрытых путей
│   ├── localization.py     # Определение национальных сегментов
│   ├── aggregator.py       # Агрегация результатов в ScanReport
│   └── report/             # Генерация JSON/HTML отчетов (Jinja2)
├── tests/                  # Pytest-модули
├── cli.py                  # CLI-точка входа (click)
├── requirements.txt        # Зависимости проекта
├── pyproject.toml          # Настройки сборки (poetry/pyproject)
├── pytest.ini              # Конфигурация pytest
└── README.md               # Документация проекта
```

---

## 🧪 Тестирование

* Запуск всех тестов:

  ```bash
  pytest --maxfail=1 --disable-warnings -q
  ```
* Проверка типизации:

  ```bash
  mypy .
  ```

---

## 🤝 Контрибьюция

1. Форкните репозиторий.
2. Создайте ветку:

   ```bash
   git checkout -b feature/my-feature
   ```
3. Внесите изменения и добавьте тесты.
4. Запустите pre-commit хуки:

   ```bash
   pre-commit run --all-files
   ```
5. Откройте Pull Request.

---

## 📜 Лицензия

Этот проект распространяется под лицензией MIT.
