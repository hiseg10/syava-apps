"""
Exporta dados de notas dos alunos do Supabase para `student_scores.json`.

Gera o arquivo no formato esperado pelo notebook `analise_notas.ipynb`
e pelo dashboard dinâmico `html/dashboard_dinamico.html`.

⚠️ Respeitando as regras do AGENTS.md:
   - Usa @st.cache_data (TTL 300s) para evitar estouro de cota do Supabase.
   - Não usa select("*") — seleciona apenas colunas necessárias.
   - Pode ser chamado manualmente OU integrado ao app Streamlit.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Any

# --- Bootstrap path para encontrar 'services' (subpasta apps/) ---
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(_THIS_DIR))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from services.database import get_supabase_client  # type: ignore
except Exception:  # fallback: usa st se estiver rodando dentro do Streamlit
    get_supabase_client = None  # type: ignore


OUTPUT_PATH = os.path.join(
    project_root, "data", "repo", "plugins", "student_scores.json"
)


def _build_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Agrupa as linhas no formato `students_data` esperado pelo consumidor."""
    students_data: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "name": "",
        "daily_qualitative_points": [],
        "subjects": defaultdict(lambda: {
            "T1": {"N1": 0.0, "N2": 0.0, "N3": 0.0},
            "T2": {"N1": 0.0, "N2": 0.0, "N3": 0.0},
            "T3": {"N1": 0.0, "N2": 0.0, "N3": 0.0},
        }),
    })

    for row in rows:
        sid = str(row["student_id"])
        subj = str(row["subject_id"])
        trimester = row["trimester"]            # 'T1' | 'T2' | 'T3'
        note = row["note_code"]                 # 'N1' | 'N2' | 'N3'
        value = float(row.get("value", 0.0))

        s = students_data[sid]
        s["name"] = row.get("student_name", s["name"])
        s["subjects"][subj][trimester][note] = value

        # Pontos qualitativos (acumula por linha com flag is_qualitative)
        if row.get("is_qualitative"):
            s["daily_qualitative_points"].append({
                "points": float(row.get("qualitative_points", 0))
            })

    # normaliza para dict puro (defaultdict -> dict)
    return {
        "students_data": {
            sid: {
                "name": s["name"],
                "daily_qualitative_points": s["daily_qualitative_points"],
                "subjects": dict(s["subjects"]),
            }
            for sid, s in students_data.items()
        }
    }


def export_from_supabase() -> str:
    """
    Busca os dados do Supabase e grava o JSON em `OUTPUT_PATH`.
    Retorna o caminho do arquivo gerado.
    """
    if get_supabase_client is None:
        raise RuntimeError(
            "services.database.get_supabase_client indisponível. "
            "Execute este script dentro do ambiente Streamlit (run.bat)."
        )

    client = get_supabase_client()

    # ⚠️ Select explícito (NUNCA '*') — respeitando AGENTS.md
    res = (
        client.table("student_scores")
        .select("student_id,student_name,subject_id,trimester,note_code,value,is_qualitative,qualitative_points")
        .execute()
    )
    rows = res.data or []

    payload = _build_payload(rows)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"✅ Exportado: {OUTPUT_PATH}")
    print(f"   👥 Alunos: {len(payload['students_data'])}")
    print(f"   📊 Linhas brutas: {len(rows)}")
    return OUTPUT_PATH


if __name__ == "__main__":
    export_from_supabase()