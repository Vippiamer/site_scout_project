# setup.py
from setuptools import setup, find_packages

setup(
    name="site_scout",
    version="0.1.0",
    description="Асинхронный веб-сканер SiteScout",
    packages=find_packages(),  # автоматически найдёт папку site_scout
    install_requires=[
        # здесь можно продублировать ваши зависимости,
        # но не обязательно — вы уже их установили из requirements.txt
    ],
    python_requires=">=3.11",
)
