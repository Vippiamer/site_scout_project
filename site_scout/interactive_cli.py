# === FILE: site_scout_project/site_scout/interactive_cli.py ===
"""
SiteScout Interactive Runner with Wordlist Update
"""
import argparse
import sys

from .config import ScannerConfig  # type: ignore[import]
from .scanner import SiteScanner  # type: ignore[import]


def main():
    parser = argparse.ArgumentParser(
        description="SiteScout Interactive Runner with Wordlist Update"
    )
    parser.add_argument("url", help="Введите URL сайта для сканирования")
    parser.add_argument(
        "--depth", type=int, default=2, help="Максимальная глубина обхода ссылок [2]"
    )
    parser.add_argument(
        "--timeout", type=int, default=120, help="Таймаут сканирования в секундах [120]"
    )

    args = parser.parse_args()
    base_url = args.url
    max_depth = args.depth
    timeout = args.timeout

    # Создаем конфигурацию сканирования
    try:
        config = ScannerConfig(
            base_url=base_url,
            max_depth=max_depth,
            timeout=timeout,
        )
    except TypeError as e:
        sys.stderr.write(f"Ошибка конфигурации ScannerConfig: {e}\n")
        sys.exit(1)

    # Запускаем сканер
    scanner = SiteScanner(config)
    results = scanner.run()

    # Вывод результатов
    for url, status in results.items():
        print(f"{url} -> {status}")


if __name__ == "__main__":  # pragma: no cover
    main()


# Unit tests for interactive_cli
import unittest  # noqa: E402


class TestScannerConfigInvocation(unittest.TestCase):
    def test_scanner_config_signature(self):
        """Проверяет, что ScannerConfig принимает ожидаемые ключевые аргументы."""
        sig = ScannerConfig.__init__.__code__.co_varnames
        # Ожидаем, что в сигнатуре присутствуют base_url, max_depth, timeout
        self.assertIn("base_url", sig)
        self.assertIn("max_depth", sig)
        self.assertIn("timeout", sig)


if __name__ == "pytest":
    # Для pytest-совместимости
    import pytest  # noqa: E402

    pytest.main()
