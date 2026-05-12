from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML config file without applying milestone 003 validation."""
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file) or {}

    if not isinstance(data, dict):
        raise ValueError("Config file must contain a YAML mapping.")

    return data

