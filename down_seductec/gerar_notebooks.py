"""Gera `aulas_S0X.ipynb` nas pastas baixadas pelo Down SeducTec.

Para cada `data/repo/<turma>/<disciplina>/S0X/seductec/` que tenha
`links_aulas.md`, cria um notebook com:

- índice navegável no topo (sidebar/âncoras);
- um cartão por aula com os links da Leitura (PDFs locais);
- player do YouTube embutido (output já gravado, sem precisar rodar a célula).

Uso:
    .sysenv\\Scripts\\python.exe apps\\down_seductec\\gerar_notebooks.py
    ... --turma "2ª SÉRIE - Turma I-A (Técnico DS)"
    ... --disciplina "PROGRAMAÇÃO PARA DISPOSITIVOS MÓVEIS" --semanas S01,S02
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys

project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell

from apps.down_seductec.seductec_downloader import (
    REPO_BASE,
    SeductecDownloader,
)

AULA_NUM = re.compile(r"Aula_(\d+)", re.IGNORECASE)


def encontrar_pastas(turma: str | None, disciplina: str | None, semanas: list[str]) -> list[str]:
    padrao = os.path.join(REPO_BASE, "*", "*", "S*", "seductec")
    encontradas = []
    for caminho in sorted(glob.glob(padrao)):
        partes = caminho.replace("\\", "/").split("/")
        t, d, s = partes[-4], partes[-3], partes[-2]
        if turma and t != turma:
            continue
        if disciplina and d != disciplina:
            continue
        if semanas and s.upper() not in semanas:
            continue
        if os.path.isfile(os.path.join(caminho, "links_aulas.md")):
            encontradas.append(caminho)
    return encontradas


def aulas_da_pasta(pasta: str) -> list[dict]:
    """Cruza links_aulas.md (vídeos) com os PDFs locais, por aula."""
    videos = SeductecDownloader._parse_links_md(os.path.join(pasta, "links_aulas.md"))
    pdfs: dict[str, list[str]] = {}
    for arq in sorted(os.listdir(pasta)):
        m = AULA_NUM.search(arq)
        if m and arq.lower().endswith(".pdf"):
            pdfs.setdefault(f"Aula_{int(m.group(1)):02d}", []).append(arq)

    aulas = []
    for chave in sorted(set(videos) | set(pdfs)):
        aulas.append(
            {
                "nome": chave,
                "videos": videos.get(chave, []),
                "pdfs": pdfs.get(chave, []),
            }
        )
    return aulas


def extrair_id_youtube(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def cartao_markdown(semana: str, disciplina: str, aula: dict, indice: bool) -> str:
    num = aula["nome"].replace("Aula_", "")
    linhas = [
        f'<a id="{aula["nome"].lower()}"></a>',
        "",
        f'<div style="background:#1f2937;color:#fff;padding:10px 16px;'
        f'border-radius:6px 6px 0 0;font-weight:bold;font-size:1.05em">'
        f'{semana.upper()} — AULA {num}</div>',
        "",
    ]
    if aula["pdfs"]:
        for pdf in aula["pdfs"]:
            rotulo = AULA_NUM.search(pdf)
            n = rotulo.group(1) if rotulo else num
            linhas.append(f"- 📄 [Leitura Aula {n}]({pdf})")
    else:
        linhas.append("- 📄 *Sem PDF nesta aula*")
    if len(aula["videos"]) > 1:
        for i, link in enumerate(aula["videos"], 1):
            linhas.append(f"- ▶️ [Vídeo da Aula {num}.{i}]({link})")
    elif not aula["videos"]:
        linhas.append("- ▶️ *Sem vídeo registrado*")
    if indice:
        linhas.append("")
        linhas.append(f"[ voltar ao índice ](#indice)")
    return "\n".join(linhas)


def indice_markdown(semana: str, disciplina: str, turma: str, aulas: list[dict]) -> str:
    linhas = [
        f'<a id="indice"></a>',
        "",
        f"# {semana.upper()} — {disciplina}",
        "",
        f"**Turma:** {turma}  ",
        f"**Gerado por:** `apps/down_seductec/gerar_notebooks.py`",
        "",
        "## Índice",
        "",
    ]
    for aula in aulas:
        num = aula["nome"].replace("Aula_", "")
        marcadores = []
        if aula["pdfs"]:
            marcadores.append("📄")
        if aula["videos"]:
            marcadores.append("▶️")
        linhas.append(
            f"- [{' '.join(marcadores)} Aula {num}](#{aula['nome'].lower()})"
        )
    linhas += [
        "",
        "> Use o painel de **TOC/Index** do Jupyter (ícone 📑) como barra lateral.",
    ]
    return "\n".join(linhas)


def celula_video(aula: dict):
    """Célula de código com o output do iframe já embutido."""
    embeds = []
    for link in aula["videos"]:
        vid = extrair_id_youtube(link)
        if vid:
            embeds.append(f"https://www.youtube.com/embed/{vid}")
    if not embeds:
        return None
    iframes = "\n".join(
        f'<iframe width="720" height="405" src="{u}" '
        f'frameborder="0" allowfullscreen style="border:1px solid #d1d5db;'
        f'border-radius:8px"></iframe>'
        for u in embeds
    )
    fonte = (
        "from IPython.display import IFrame, display\n"
        + "\n".join(
            f'display(IFrame("{u}", width=720, height=405))' for u in embeds
        )
    )
    cel = new_code_cell(source=fonte)
    cel.outputs = [
        nbformat.v4.new_output(
            output_type="display_data",
            data={"text/html": iframes},
            metadata={},
        )
    ]
    cel.execution_count = None
    return cel


def gerar_notebook(pasta: str) -> tuple[str, int]:
    turma, disciplina, semana = (
        pasta.replace("\\", "/").split("/")[-4],
        pasta.replace("\\", "/").split("/")[-3],
        pasta.replace("\\", "/").split("/")[-2],
    )
    aulas = aulas_da_pasta(pasta)
    if not aulas:
        raise ValueError(f"Nenhuma aula em {pasta}")

    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nb.metadata["sysava"] = {
        "turma": turma,
        "disciplina": disciplina,
        "semana": semana,
        "gerador": "apps/down_seductec/gerar_notebooks.py",
    }

    nb.cells.append(new_markdown_cell(indice_markdown(semana, disciplina, turma, aulas)))
    for aula in aulas:
        nb.cells.append(new_markdown_cell(cartao_markdown(semana, disciplina, aula, indice=False)))
        cel = celula_video(aula)
        if cel is not None:
            nb.cells.append(cel)

    nbformat.validate(nb)
    destino = os.path.join(pasta, f"aulas_{semana}.ipynb")
    with open(destino, "w", encoding="utf-8") as fh:
        nbformat.write(nb, fh)
    return destino, len(aulas)


def assinar(caminhos: list[str]) -> bool:
    """Assina os notebooks para o HTML dos iframes renderizar sem 'Trust'."""
    try:
        from nbformat.sign import NotebookNotary

        notary = NotebookNotary()
        for caminho in caminhos:
            with open(caminho, "r", encoding="utf-8") as fh:
                nb = nbformat.read(fh, as_version=4)
            notary.sign(nb)
            with open(caminho, "w", encoding="utf-8") as fh:
                nbformat.write(nb, fh)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[AVISO] Assinatura pulada: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera aulas_S0X.ipynb nas pastas baixadas")
    parser.add_argument("--turma", help="Filtrar por turma exata")
    parser.add_argument("--disciplina", help="Filtrar por disciplina exata")
    parser.add_argument("--semanas", default="", help="Ex.: S01,S06")
    args = parser.parse_args()

    semanas = [s.strip().upper() for s in args.semanas.split(",") if s.strip()]
    pastas = encontrar_pastas(args.turma, args.disciplina, semanas)
    if not pastas:
        print("Nenhuma pasta com links_aulas.md encontrada.")
        return 1

    gerados = []
    for pasta in pastas:
        destino, n_aulas = gerar_notebook(pasta)
        rel = os.path.relpath(destino, project_root)
        gerados.append(destino)
        print(f"[OK] {rel} ({n_aulas} aulas)")

    assinar(gerados)
    print(f"\n{len(gerados)} notebook(s) gerado(s) e assinado(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
