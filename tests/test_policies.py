import re

import pytest

from emporio.config import RAW_DIR
from emporio.text import normalize
from emporio.tools.policies import consultar_politica, load_sections

EXPECTED = ["1", "1.2", "2", "3", "3.1", "4", "4.1", "4.2", "4.3", "4.4", "5.1", "5.2", "5.3",
            "6.1", "6.2", "7", "7.1", "7.2", "7.3", "8.1", "8.2", "8.3", "9", "10"]


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize(text))


def test_all_sections_present():
    assert list(load_sections()) == EXPECTED


def test_policies_md_matches_pdf():
    """Cada frase do policies.md (fora das tabelas reescritas) precisa existir no PDF."""
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(RAW_DIR / "politicas_da_loja.pdf")
    pdf = _squash(" ".join(page.extract_text() for page in reader.pages))
    rewritten_tables = {"1.2", "2", "3", "5.2"}
    for num, sec in load_sections().items():
        if num in rewritten_tables:
            continue
        for sentence in re.split(r"(?<=[.:])\s+|\n", sec["texto"]):
            s = _squash(re.sub(r"^(- |\d\. )", "", sentence))
            if len(s) > 25:
                assert s in pdf, f"§{num}: trecho não encontrado no PDF: {sentence[:80]}"


def test_consultar_politica_returns_exact_text_and_notes():
    r = consultar_politica("4.1")
    assert r["secao"].startswith("§4.1")
    assert "7 (sete) dias corridos" in r["texto"]
    assert "90 dias" in consultar_politica("4.2")["nota_de_interpretacao"]
    assert "erro" in consultar_politica("99")
