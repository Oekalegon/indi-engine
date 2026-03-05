from pathlib import Path
import yaml

DEFAULT_CONFIG_PATH = Path("config/main.yaml")


def load(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)
