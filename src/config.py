from pathlib import Path
import json

ROOT = Path(__file__).parent.parent


def load_tags():
    with open(ROOT / "config" / "tags.json", "r", encoding="utf-8") as f:
        return json.load(f)


def get_available_tags():
    return load_tags()

def save_tags(tags):
    path = ROOT / "config" / "tags.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tags, f, ensure_ascii=False, indent=2)
