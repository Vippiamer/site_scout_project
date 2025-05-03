# site_scout/crawler/robots.py
"""
Parser and checker for robots.txt rules.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class RobotsTxtRules:
    """Parser and checker for robots.txt rules."""

    def __init__(self, text: str) -> None:
        self.groups: List[Dict[str, Any]] = []
        self._parse(text)

    def can_fetch(self, user_agent: str, path: str) -> bool:
        """Return True if the user_agent can fetch the given path under the rules."""
        group = self._match_group(user_agent)
        if not group:
            return True
        allowed = True
        for directive, rule in group.get("directives", []):
            if rule and path.startswith(rule):
                allowed = directive == "allow"
        return allowed

    def _parse(self, text: str) -> None:
        """Parse robots.txt content into user-agent groups and directives."""
        current: Optional[Dict[str, Any]] = None
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            key, _, val = line.partition(":")
            key = key.strip().lower()
            val = val.strip()
            if key == "user-agent":
                current = {"agents": [val], "directives": []}
                self.groups.append(current)
            elif key in ("allow", "disallow") and current is not None:
                # skip empty disallow (means allow all)
                if key == "disallow" and not val:
                    continue
                current["directives"].append((key, val))

    def _match_group(self, ua: str) -> Optional[Dict[str, Any]]:
        """Select the most specific group matching the user-agent."""
        ua = ua.lower()
        for group in self.groups:
            for agent in group.get("agents", []):
                if agent == "*" or ua.startswith(agent.lower()):
                    return group
        return None
