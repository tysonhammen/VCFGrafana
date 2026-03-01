"""Minimal setup.py for editable install (PEP 660) compatibility with older setuptools."""
from setuptools import setup, find_packages

setup(
    name="vcenter-exporter",
    version="0.1.0",
    packages=find_packages(where=".", include=["vcenter_exporter*"]),
    install_requires=[
        "requests>=2.28.0",
        "prometheus_client>=0.19.0",
        "python-dotenv>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "vcenter-exporter=vcenter_exporter.main:main",
        ],
    },
    python_requires=">=3.10",
)
