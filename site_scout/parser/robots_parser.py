# --------------------------------------------------------
# site_scout/parser/robots_parser.py
"""
Модуль: robots_parser.py

Парсинг robots.txt и извлечение правил.
- Сбор секций для конкретного User-Agent и wildcard
- Извлечение разрешённых и запрещённых путей
- Определение crawl-delay (если задан)
"""
from dataclasses import dataclass, field
from typing import List, Optional
import aiohttp

@dataclass
class RobotsRules:
    user_agent: str
    allowed: List[str] = field(default_factory=list)
    disallowed: List[str] = field(default_factory=list)
    crawl_delay: Optional[float] = None


async def parse_robots(robots_url: str, user_agent: str) -> RobotsRules:
    """
    Асинхронно загружает и парсит robots.txt.

    :param robots_url: полный URL до robots.txt
    :param user_agent: целевой User-Agent (например, 'SiteScoutBot/1.0')
    :return: RobotsRules с путями allow, disallow и crawl_delay

    Пример:
    ```python
    from site_scout.parser.robots_parser import parse_robots

    rules = asyncio.run(parse_robots(
        "https://example.com/robots.txt",
        "SiteScoutBot/1.0"
    ))
    print(rules.disallowed)
    print(rules.allowed)
    print(rules.crawl_delay)
    ```
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(robots_url) as resp:
            text = await resp.text()
    lines = text.splitlines()
    rules = RobotsRules(user_agent=user_agent)
    current_agents: List[str] = []
    for raw in lines:
        line = raw.split('#', 1)[0].strip()
        if not line:
            continue
        if ':' not in line:
            continue
        key, value = [part.strip() for part in line.split(':', 1)]
        key_low = key.lower()
        # User-agent
        if key_low == 'user-agent':
            # новая секция
            current_agents = [ua.strip() for ua in value.split()]
        # Disallow
        elif key_low == 'disallow' and any(
                ua == '*' or ua.lower() in user_agent.lower()
                for ua in current_agents
        ):
            rules.disallowed.append(value)
        # Allow
        elif key_low == 'allow' and any(
                ua == '*' or ua.lower() in user_agent.lower()
                for ua in current_agents
        ):
            rules.allowed.append(value)
        # Crawl-delay
        elif key_low == 'crawl-delay' and any(
                ua == '*' or ua.lower() in user_agent.lower()
                for ua in current_agents
        ):
            try:
                rules.crawl_delay = float(value)
            except ValueError:
                pass
    return rules

