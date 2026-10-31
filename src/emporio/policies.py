"""The internal policy manual, loaded from a committed text extract.

`policies.txt` is produced once from `data/políticas_da_loja.pdf` with
`pdftotext -layout` and committed, so running the agent does not require poppler.
See `scripts/extract_policies.sh` to regenerate it.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

POLICY_FILE = Path(__file__).with_name("policies.txt")

_HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+(\S.*)$")
_NOISE = re.compile(r"^\s*(Página \d+|Empório da Música\s+Manual de Políticas e Procedimentos)\s*$")


@lru_cache(maxsize=1)
def full_text() -> str:
    return POLICY_FILE.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def sections() -> dict[str, str]:
    """Map section number ("4.1") to its text, including nested subsections."""
    result: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in full_text().splitlines():
        if _NOISE.match(line):
            continue
        match = _HEADING.match(line)
        # headings look like "4. Política de Trocas" or "4.1 Direito de Arrependimento"
        if match and len(match.group(2)) > 2 and not line.strip().startswith(("#", "|")):
            number = match.group(1)
            if current is not None:
                result[current] = "\n".join(buffer).strip()
            current = number
            buffer = [line.strip()]
        elif current is not None:
            buffer.append(line)
    if current is not None:
        result[current] = "\n".join(buffer).strip()
    return result


def get_policy(section: str) -> dict:
    """Return the text of a manual section so it can be quoted with an exact citation.

    A parent section (e.g. "4") returns its own text followed by every subsection, so a citation of
    §4 carries 4.1–4.4 with it.
    """
    section = str(section).strip().rstrip(".")
    known = sections()
    children = {
        key: value for key, value in known.items() if key.startswith(section + ".")
    }
    if section in known or children:
        parts = [known[section]] if section in known else []
        parts += [value for key, value in sorted(children.items())]
        return {"section": section, "text": "\n\n".join(parts), "found": True}
    matches = {k: v for k, v in known.items() if section.lower() in v.lower()}
    if matches:
        first = next(iter(matches.items()))
        return {"section": first[0], "text": first[1], "found": True, "note": "seção aproximada"}
    return {
        "found": False,
        "section": section,
        "available": sorted(known),
        "note": "seção não encontrada; use o manual completo do contexto",
    }
