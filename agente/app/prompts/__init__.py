from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


def load_prompt(relative_path: str) -> str:
    return (PROMPTS_DIR / relative_path).read_text(encoding="utf-8")
