# File: site_scout/parser/robots_parser.py
"""site_scout.parser.robots_parser: Асинхронный парсер robots.txt и извлечение правил."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import aiohttp


@dataclass
class RobotsRules:
    """Хранит правила из robots.txt для заданного User-Agent."""

    user_agent: str
    allowed: List[str] = field(default_factory=list)
    disallowed: List[str] = field(default_factory=list)
    crawl_delay: Optional[float] = None


async def parse_robots(robots_url: str, user_agent: str) -> RobotsRules:
    """Асинхронно загружает и парсит robots.txt, возвращает RobotsRules.

    Args:
        robots_url: полный URL до robots.txt.
        user_agent: целевой User-Agent.

    Returns:
        RobotsRules с полями allowed, disallowed и crawl_delay.
    """
    text = await _fetch_robots(robots_url)
    lines = _prepare_lines(text)
    rules = RobotsRules(user_agent=user_agent)
    current_agents: List[str] = []

    for directive, value in lines:
        _process_directive(directive, value, current_agents, user_agent, rules)

    return rules


def _process_directive(
    directive: str,
    value: str,
    current_agents: List[str],
    user_agent: str,
    rules: RobotsRules,
) -> None:
    """Обрабатывает одну директиву из robots.txt и обновляет rules/current_agents."""
    if directive == "user-agent":
        current_agents.clear()
        current_agents.extend([ua.strip() for ua in value.split()])
    elif directive in ("allow", "disallow") and _matches_agent(current_agents, user_agent):
        if directive == "allow":
            rules.allowed.append(value)
        elif value:
            rules.disallowed.append(value)
    elif directive == "crawl-delay" and _matches_agent(current_agents, user_agent):
        try:
            rules.crawl_delay = float(value)
        except ValueError:
            pass


async def _fetch_robots(url: str) -> str:
    """Загружает содержимое robots.txt по URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()


def _prepare_lines(text: str) -> List[Tuple[str, str]]:
    """Очищает текст от комментариев и разделяет на (директива, значение)."""
    lines: List[Tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, val = (part.strip() for part in line.split(":", 1))
        lines.append((key.lower(), val))
    return lines


def _matches_agent(agents: List[str], user_agent: str) -> bool:
    """Проверяет, соответствует ли список агентов заданному user_agent."""
    ua = user_agent.lower()
    return any(agent == "*" or agent.lower() in ua for agent in agents)
