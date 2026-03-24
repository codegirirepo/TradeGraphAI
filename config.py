"""Centralized configuration loader — reads config.yaml."""

import yaml
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
_config = {}


def _load():
    global _config
    if not _config and _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            _config = yaml.safe_load(f) or {}
    return _config


def get(section: str, key: str, default=None):
    """Get a config value: get('risk', 'high_volatility', 0.50)"""
    cfg = _load()
    return cfg.get(section, {}).get(key, default)
