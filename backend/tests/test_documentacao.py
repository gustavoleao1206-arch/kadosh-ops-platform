"""A documentação não pode conter comando quebrado.

Aconteceu de verdade: `scripts\\apk.ps1` foi gravado no RUNBOOK como `scripts` +
byte 0x07 + `pk.ps1`, e `X:\\dev\\avd` virou `X:\\dev` + 0x07 + `vd`. No editor parece certo — o
byte de campainha é invisível —, mas quem copiasse a linha rodava um comando que não existe.

A causa é sempre a mesma: um caminho do Windows escrito dentro de uma string que passa por mais uma
camada de interpretação de escape. `\\a` vira campainha, `\\t` vira tabulação, `\\b`, `\\f`, `\\v` e
`\\0` também têm significado. Escrever a documentação por uma ferramenta que não reinterpreta
escapes (ou montar a barra invertida com `chr(92)`) evita o problema; este teste garante que, se
voltar, o build reclama antes de alguém copiar a linha.
"""

import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parents[2]

ARQUIVOS = sorted(
    p
    for p in list(RAIZ.rglob("*.md")) + list((RAIZ / "scripts").glob("*.ps1"))
    if not any(x in p.parts for x in (".git", "node_modules", ".venv", "build", "dist", "coverage"))
)

# O que um escape comido deixa para trás. TAB fica de fora: em documento é indentação legítima,
# e o caso do meio da palavra é tratado à parte.
CONTROLES = {
    "\x00": "\\0",
    "\x07": "\\a",
    "\x08": "\\b",
    "\x0b": "\\v",
    "\x0c": "\\f",
}


@pytest.mark.parametrize("caminho", ARQUIVOS, ids=lambda p: str(p.relative_to(RAIZ)))
def test_sem_byte_de_controle(caminho: pathlib.Path):
    texto = caminho.read_text(encoding="utf-8-sig", errors="replace")
    for numero, linha in enumerate(texto.splitlines(), 1):
        for byte, escape in CONTROLES.items():
            assert byte not in linha, (
                f"{caminho.relative_to(RAIZ)}:{numero} tem o byte {byte!r} — quase certamente um "
                f"{escape} de caminho do Windows que foi interpretado. Reescreva a linha sem passar "
                f"o texto por uma camada que reinterprete escapes."
            )


@pytest.mark.parametrize("caminho", ARQUIVOS, ids=lambda p: str(p.relative_to(RAIZ)))
def test_sem_tabulacao_no_meio_de_palavra(caminho: pathlib.Path):
    """TAB entre dois caracteres não-espaço é `\\t` de caminho, não formatação."""
    texto = caminho.read_text(encoding="utf-8-sig", errors="replace")
    for numero, linha in enumerate(texto.splitlines(), 1):
        for i, c in enumerate(linha):
            if c != "\t" or i == 0 or i + 1 >= len(linha):
                continue
            assert not (linha[i - 1].strip() and linha[i + 1].strip()), (
                f"{caminho.relative_to(RAIZ)}:{numero} tem TAB no meio de uma palavra — "
                f"provavelmente `\\t` de um caminho (X:\\dev\\tools) que virou tabulação."
            )


def test_comandos_do_runbook_apontam_para_scripts_que_existem():
    """Comando documentado que aponta para script inexistente é a versão visível do mesmo problema."""
    import re

    scripts = {p.name.lower() for p in (RAIZ / "scripts").glob("*.ps1")}
    citados: set[str] = set()
    for doc in (RAIZ / "docs/RUNBOOK.md", RAIZ / "README.md"):
        if not doc.exists():
            continue
        citados |= {m.lower() for m in re.findall(r"scripts[\\/]([\w.-]+\.ps1)", doc.read_text(encoding="utf-8-sig"))}

    assert citados, "nenhum script citado na documentação — o padrão de busca deve ter quebrado"
    faltando = citados - scripts
    assert not faltando, f"a documentação cita script que não existe: {sorted(faltando)}"
