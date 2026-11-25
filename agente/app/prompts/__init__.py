from pathlib import Path

PROMPTS_DIR = Path(__file__).parent


def load_prompt(relative_path: str) -> str:
    return (PROMPTS_DIR / relative_path).read_text(encoding="utf-8")


def _fields(block: str) -> tuple[dict[str, str], str]:
    """Campos `- chave: valor` e o texto livre de um trecho. Citações (`>`) são comentários."""
    fields: dict[str, str] = {}
    prose = []
    for line in filter(None, map(str.strip, block.splitlines())):
        if line.startswith(("#", ">")):
            continue
        if not line.startswith("- "):
            prose.append(line)
            continue
        key, separator, value = line[2:].partition(":")
        if not separator or not value.strip() or key in fields:
            raise ValueError(f"linha inválida ou campo repetido: {line}")
        fields[key] = value.strip()
    return fields, " ".join(prose)


def parse_catalog(markdown: str) -> dict:
    """Lê um catálogo de critérios em Markdown: cabeçalho e um critério por título `##`.

    Só separa o texto. Quem confere campos, pesos e fases é o `CriteriaCatalog`, então um erro
    de digitação impede o agente de subir em vez de passar despercebido.
    """
    header, *sections = ("\n" + markdown).split("\n## ")
    catalog, _ = _fields(header)
    criteria = []
    for section in sections:
        title, _, body = section.partition("\n")
        fields, description = _fields(body)
        fields["fundamentos"] = [
            item.strip() for item in fields.get("fundamentos", "").split(";") if item.strip()
        ]
        criteria.append({"nome": title.strip(), "descricao": description, **fields})
    return {**catalog, "criterios": criteria}
