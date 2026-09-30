"""
Acompanhamento de Planejamento e Registro no Portal (SysAva)

App Streamlit autônomo (NÃO depende da API HTTP). Faz tudo localmente:
  - Lê o SQLite local: data/escola_ativa.db
  - Gera planos (.txt) chamando o gerador como biblioteca
  - Registra no portal chamando o robô Selenium (subprocesso)
  - Raspagem do portal (subprocesso) e leitura do status em data/logs/registro_status.json

Navegação pelo sidebar (contexto de turma/disciplina sempre acessível).
Ciclo: Planejamento -> Geração de planos -> Registro no portal -> Auditoria.
"""

import os
import re
import sys
import io
import json
import html
import zipfile
import subprocess
from datetime import datetime, date

import streamlit as st
import pandas as pd
import altair as alt

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

API_DIR = os.path.join(PROJECT_ROOT, "apps", "api")
APPS_DIR = os.path.join(PROJECT_ROOT, "apps")
for _p in (APPS_DIR, API_DIR, os.path.join(API_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Núcleo compartilhado do app (sem FastAPI / sem api_service)
from apps.planejamento_registro.core import banco as core_banco
from apps.planejamento_registro.core import datas as core_datas
from apps.planejamento_registro.core.gerador import gerar_txt_planos as _gerar_txt_planos

DB_PATH = core_banco.DB_PATH
AULAS_DIR = core_banco.AULAS_DIR
LOGS_DIR = os.path.join(PROJECT_ROOT, "data", "logs")
REGISTRO_STATUS = os.path.join(LOGS_DIR, "registro_status.json")

st.set_page_config(page_title="Planejamento e Registro", page_icon="🗂️", layout="wide")


# ===========================================================================
# Banco
# ===========================================================================
def get_db():
    return core_banco.get_db()


def get_config(chave, default=None):
    return core_banco.get_config(chave, default)


def set_config(chave, valor):
    return core_banco.set_config(chave, valor)


@st.cache_data(ttl=300, show_spinner=False)
def _nome_turma_atual(turma_code):
    """Nome canônico atual da turma — a raspagem grava o histórico com ele.

    Filtra linhas residuais gravadas com nomes antigos (duplicatas), alinhando
    a contagem local com o que o portal iSeduc realmente exibe.
    """
    conn = get_db()
    try:
        row = conn.execute("SELECT name FROM classes WHERE code = ?", (str(turma_code),)).fetchone()
        return row["name"] if row else str(turma_code)
    finally:
        conn.close()


# ===========================================================================
# Ações (sem API HTTP)
# ===========================================================================
def gerar_planos(turma_code, disciplina_id, output_dir="pendentes", force=False,
                 estrategia=None, aula_min=None, aula_max=None):
    """Gera os planos pelo núcleo compartilhado (sem servidor)."""
    return _gerar_txt_planos(
        output_dir=output_dir,
        force_overwrite=force,
        turma_id=str(turma_code),
        disciplina_id=str(disciplina_id),
        estrategia=estrategia,
        aula_min=aula_min,
        aula_max=aula_max,
    )


# ===========================================================================
# Tipos de estratégia (lista configurável, persistida em master_config)
# ===========================================================================
_ESTRATEGIAS_DEFAULT = [
    "Aula expositiva",
    "Aula baseada em projetos",
    "Aula de atividades em laboratório",
]


def _estrategias_disponiveis():
    raw = core_banco.get_config("estrategias_disponiveis")
    if isinstance(raw, list) and raw:
        return [str(x).strip() for x in raw if str(x).strip()]
    if raw:
        try:
            lista = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(lista, list) and lista:
                return [str(x).strip() for x in lista if str(x).strip()]
        except Exception:
            pass
    return list(_ESTRATEGIAS_DEFAULT)


def _salvar_estrategias(lista):
    core_banco.set_config("estrategias_disponiveis", list(lista))


def _python() -> str:
    return sys.executable or "python"


def registrar_planos(files=None, all_files=False):
    script = os.path.join(API_DIR, "tools", "registrar_aulas.py")
    cmd = [_python(), "-u", script]
    if all_files:
        cmd.append("--all")
    elif files:
        cmd.extend(["--files", ",".join(files)])
    else:
        return False, "Nenhum plano selecionado."
    try:
        subprocess.Popen(cmd, cwd=PROJECT_ROOT)
        return True, "Registro iniciado em segundo plano (o navegador vai abrir)."
    except Exception as e:
        return False, str(e)


def rodar_raspagem():
    script = os.path.join(API_DIR, "tools", "bot_raspagem.py")
    try:
        subprocess.Popen([_python(), "-u", script], cwd=PROJECT_ROOT)
        return True, "Raspagem iniciada em segundo plano (o navegador vai abrir)."
    except Exception as e:
        return False, str(e)


def ler_registro_status():
    if not os.path.exists(REGISTRO_STATUS):
        return None
    try:
        with open(REGISTRO_STATUS, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


# ===========================================================================
# Helpers de domínio
# ===========================================================================
def _is_num(v) -> bool:
    return str(v).strip().isdigit()


def monitor_limite():
    conn = get_db()
    rows = [dict(r) for r in conn.execute(
        "SELECT turma_id, disciplina_id, COUNT(*) AS planos FROM planejamento "
        "GROUP BY turma_id, disciplina_id ORDER BY turma_id, disciplina_id")]
    out = []
    for r in rows:
        nome, maxh = None, 40
        if _is_num(r["disciplina_id"]):
            sub = conn.execute("SELECT name, max_hours FROM subjects WHERE id = ?",
                               (r["disciplina_id"],)).fetchone()
            if sub:
                nome = sub["name"]
                maxh = sub["max_hours"] or 40
        out.append({
            "turma_id": r["turma_id"],
            "disciplina_id": r["disciplina_id"],
            "Disciplina": nome or "?",
            "Planos": r["planos"],
            "Limite": int(maxh),
            "Excedente": max(0, r["planos"] - int(maxh)),
            "Excede": r["planos"] > int(maxh),
        })
    conn.close()
    return out


def planejamento_suspeitos():
    conn = get_db()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, turma_id, disciplina_id, data_planejada, horario FROM planejamento")]
    conn.close()
    sus = []
    for r in rows:
        t, d = str(r["turma_id"]), str(r["disciplina_id"])
        if ("\\" in t) or ("/" in t) or (":" in t) or (not d.strip().isdigit()):
            sus.append(r)
    return sus


def remover_suspeitos():
    sus = planejamento_suspeitos()
    ids = [r["id"] for r in sus]
    if not ids:
        return 0
    conn = get_db()
    conn.execute("DELETE FROM planejamento WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)
    conn.commit()
    conn.close()
    return len(ids)


def reset_planejamento(turma_id=None, disciplina_id=None):
    conn = get_db()
    if turma_id is None:
        n = conn.execute("DELETE FROM planejamento").rowcount
    elif disciplina_id is None:
        n = conn.execute("DELETE FROM planejamento WHERE turma_id = ?", (str(turma_id),)).rowcount
    else:
        n = conn.execute("DELETE FROM planejamento WHERE turma_id = ? AND disciplina_id = ?",
                         (str(turma_id), str(disciplina_id))).rowcount
    conn.commit()
    conn.close()
    return n


# ===========================================================================
# Carregamento de dados
# ===========================================================================
@st.cache_data(ttl=30, show_spinner=False)
def load_classes():
    conn = get_db()
    rows = [dict(r) for r in conn.execute("SELECT id, name, code FROM classes ORDER BY name")]
    conn.close()
    return rows


@st.cache_data(ttl=30, show_spinner=False)
def load_subjects_for_class(class_id):
    conn = get_db()
    rows = [dict(r) for r in conn.execute(
        """SELECT s.id, s.name, s.max_hours, s.duration_type, cs.is_active
             FROM class_subjects cs
             JOIN subjects s ON s.id = cs.subject_id
            WHERE cs.class_id = ?
            ORDER BY s.name""", (class_id,)
    )]
    conn.close()
    return rows


@st.cache_data(ttl=20, show_spinner=False)
def panel_data(turma_code, disciplina_id):
    ids = _disc_ids(turma_code, disciplina_id)
    nome = _nome_turma_atual(turma_code)
    ph = ",".join("?" * len(ids))
    conn = get_db()
    reg = conn.execute(
        f"SELECT COUNT(*) FROM historico_aulas WHERE turma_id = ? AND disciplina_id IN ({ph}) "
        "AND turma = ? AND (status IS NULL OR status NOT LIKE 'Aula Exclu%')",
        (str(turma_code), *ids, nome)).fetchone()[0]
    datas = [r[0] for r in conn.execute(
        f"SELECT data_aula FROM historico_aulas WHERE turma_id = ? AND disciplina_id IN ({ph}) "
        "AND turma = ? AND (status IS NULL OR status NOT LIKE 'Aula Exclu%')",
        (str(turma_code), *ids, nome))]
    plan = conn.execute(
        f"SELECT COUNT(*) FROM planejamento WHERE turma_id = ? AND disciplina_id IN ({ph}) AND status IN ('pendente','pronta')",
        (str(turma_code), *ids)).fetchone()[0]
    carga = conn.execute("SELECT max_hours FROM subjects WHERE id = ?", (disciplina_id,)).fetchone()
    conn.close()
    validos = [d for d in datas if _data_dt(d)]
    ult = max(validos, key=_data_dt) if validos else None
    return {"registradas": reg, "ultima_data": ult, "planejadas": plan,
            "carga": (carga[0] if carga and carga[0] else 40)}


@st.cache_data(ttl=20, show_spinner=False)
def listar_historico(turma_code, disciplina_id):
    ids = _disc_ids(turma_code, disciplina_id)
    nome = _nome_turma_atual(turma_code)
    ph = ",".join("?" * len(ids))
    conn = get_db()
    rows = [dict(r) for r in conn.execute(
        f"""SELECT data_aula, horario, status FROM historico_aulas
             WHERE turma_id = ? AND disciplina_id IN ({ph}) AND turma = ?""",
        (str(turma_code), *ids, nome))]
    conn.close()
    rows.sort(key=lambda r: _data_dt(r["data_aula"]) or datetime.min, reverse=True)
    return rows


@st.cache_data(ttl=20, show_spinner=False)
def listar_planejamento(turma_code, disciplina_id):
    ids = _disc_ids(turma_code, disciplina_id)
    ph = ",".join("?" * len(ids))
    conn = get_db()
    rows = [dict(r) for r in conn.execute(
        f"""SELECT id, data_planejada, horario, numero_aula, status FROM planejamento
             WHERE turma_id = ? AND disciplina_id IN ({ph}) ORDER BY data_planejada ASC""",
        (str(turma_code), *ids))]
    conn.close()
    return rows


# ===========================================================================
# Consolidadas (visão anual: carga × fluxo por turma/disciplina)
# ===========================================================================
@st.cache_data(ttl=300, show_spinner=False)
def load_janelas_disciplinas():
    """`disciplina_id` → janela do fluxo letivo (início/fim/carga).

    Fonte primária: `master_config['calendario_letivo.json']` (a mesma que o
    gerador usa); fallback: `data/calendario_letivo.json`. Cada restrição em
    `restricoes_planejamento` traz `disciplina_ids` (espelhado nas 2 fontes).
    """
    cal = None
    try:
        from tools import database_model
        cal = database_model.get_config("calendario_letivo.json", PROJECT_ROOT)
    except Exception:
        cal = None
    if not isinstance(cal, dict):
        try:
            with open(os.path.join(PROJECT_ROOT, "data", "calendario_letivo.json"),
                      "r", encoding="utf-8") as fh:
                cal = json.load(fh)
        except Exception:
            return {}
    idx = {}
    for chave, v in (cal.get("restricoes_planejamento") or {}).items():
        if not isinstance(v, dict):
            continue
        ini = _data_dt(v.get("data_inicio"))
        fim = _data_dt(v.get("data_fim"))
        if not ini or not fim:
            continue
        for sid in v.get("disciplina_ids") or []:
            idx[str(sid)] = {"chave": str(chave), "inicio": ini, "fim": fim,
                             "carga": v.get("carga_horaria")}
    return idx


def _turma_curta(nome):
    """Sigla curta da turma (ex.: '2ª SÉRIE - Turma I-A (Técnico DS)' → 'I-A')."""
    m = re.search(r"Turma\s+([0-9A-Za-z\-]+)", str(nome) or "")
    return m.group(1) if m else str(nome)


def _chave_disc(nome):
    """Chave canônica da disciplina para agrupar aliases numa só linha.

    Remove sufixos de turma `(...)`, variantes `2026A/2026B`, acentos e caixa:
    'PROGRAMAÇÃO WEB FRONT-END 2026A' e 'PROGRAMAÇÃO WEB FRONT-END (2ª SÉRIE...)'
    viram a mesma chave que 'PROGRAMAÇÃO WEB FRONT-END'.
    """
    import unicodedata
    s = str(nome or "")
    s = re.sub(r"\s*\(.*\)\s*$", "", s)
    s = re.sub(r"\s+20\d\d[A-Za-z]\s*$", "", s)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", " ", s).strip().upper()


@st.cache_data(ttl=30, show_spinner=False)
def consolidadas_data(turma_filtro=None):
    """Consolida, por turma×disciplina: carga anual, registradas (portal),
    prontas/pendentes (.txt gerados), fila (planejamento) e faltantes.

    `turma_filtro` = code da turma (str) ou None para todas as turmas.
    """
    classes = load_classes()
    janelas = load_janelas_disciplinas()
    # Índice de arquivos .txt gerados: (pasta, turma_id, disciplina_id) -> qtd
    txt_idx = {}
    for pasta in ("prontas", "pendentes"):
        for it in listar_planos(pasta):
            k = (pasta, str(it["turma_id"]), str(it["disciplina_id"]))
            txt_idx[k] = txt_idx.get(k, 0) + 1
    conn = get_db()
    linhas = []
    try:
        for c in classes:
            code = str(c["code"])
            if turma_filtro and code != str(turma_filtro):
                continue
            nome = _nome_turma_atual(c["code"])
            hist = {}
            for tid, did, n in conn.execute(
                "SELECT turma_id, disciplina_id, COUNT(*) FROM historico_aulas "
                "WHERE turma_id = ? AND turma = ? "
                "AND (status IS NULL OR status NOT LIKE 'Aula Exclu%') "
                "GROUP BY turma_id, disciplina_id",
                (code, nome),
            ):
                hist[(str(tid), str(did))] = n
            fila = {}
            for did, n in conn.execute(
                "SELECT disciplina_id, COUNT(*) FROM planejamento "
                "WHERE turma_id = ? AND status IN ('pendente','pronta') "
                "GROUP BY disciplina_id",
                (code,),
            ):
                fila[str(did)] = n
            grupos = {}
            for s in load_subjects_for_class(c["id"]):
                if _chave_disc(s["name"]).startswith("CADERNO DE ATIVIDADES"):
                    continue  # item de apoio, fora da carga letiva (Escola.txt)
                chave = _chave_disc(s["name"])
                grupos.setdefault(chave, []).append(s)
            for chave, membros in grupos.items():
                # Alias (ex.: '4' e '30', '6', '31', '33', '34') = UMA disciplina
                ids = set()
                for m in membros:
                    ids.update(_disc_ids(c["code"], m["id"]))
                    ids.add(str(m["id"]))
                ids = sorted(ids)
                reg = sum(hist.get((code, i), 0) for i in ids)
                fl = sum(fila.get(i, 0) for i in ids)
                pr = sum(txt_idx.get(("prontas", code, i), 0) for i in ids)
                pe = sum(txt_idx.get(("pendentes", code, i), 0) for i in ids)
                carga = max(int(m["max_hours"]) if m.get("max_hours") else 40
                            for m in membros)
                jan = None
                for i in ids:
                    if i in janelas:
                        jan = janelas[i]
                        break
                linhas.append({
                    "turma": c["name"],
                    "turma_code": code,
                    "turma_curta": _turma_curta(c["name"]),
                    "disciplina": membros[0]["name"],
                    "disciplina_id": membros[0]["id"],
                    "ativa": any(str(m.get("is_active")) == "1" for m in membros),
                    "carga": carga,
                    "registradas": reg,
                    "prontas": pr,
                    "pendentes": pe,
                    "fila": fl,
                    "faltantes": max(0, carga - reg - pr - pe),
                    "janela_inicio": jan["inicio"] if jan else None,
                    "janela_fim": jan["fim"] if jan else None,
                    "janela_chave": jan["chave"] if jan else "",
                })
    finally:
        conn.close()
    return linhas


def listar_planos(subdir: str):
    folder = os.path.join(AULAS_DIR, subdir)
    itens = []
    if not os.path.isdir(folder):
        return itens
    for f in sorted(os.listdir(folder)):
        if not f.lower().endswith(".txt"):
            continue
        m = re.match(r"plano_(\d+)_(\d+)_(\d{4}-\d{2}-\d{2})_([0-9A-Za-z]+)", f)
        itens.append({
            "arquivo": f,
            "turma_id": m.group(1) if m else "",
            "disciplina_id": m.group(2) if m else "",
            "data": m.group(3) if m else "",
            "hora": m.group(4) if m else "",
        })
    return itens


def ler_plano_local(subdir: str, arquivo: str) -> str:
    caminho = os.path.join(AULAS_DIR, subdir, arquivo)
    try:
        with open(caminho, "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception as e:
        return f"Erro ao ler arquivo: {e}"


def excluir_plano(pasta: str, arquivo: str):
    """Remove o .txt e a linha correspondente em `planejamento`.

    Retorna (arquivo_removido, linhas_removidas_no_banco, mensagem).
    """
    caminho = os.path.join(AULAS_DIR, pasta, arquivo)
    conteudo = ler_plano_local(pasta, arquivo)
    meta, _ = parse_plano_txt(conteudo)

    removido = False
    if os.path.exists(caminho):
        try:
            os.remove(caminho)
            removido = True
        except Exception as e:
            return False, 0, f"Erro ao remover arquivo: {e}"

    linhas = 0
    turma_id, disc_id = meta.get("TURMA_ID"), meta.get("DISCIPLINA_ID")
    data, aula = meta.get("DATA"), meta.get("AULA_NUM")
    # Só apaga a linha do banco quando o AULA_NUM é conhecido (evita exclusão ampla).
    if turma_id and data and aula and str(aula).strip().isdigit():
        try:
            ids = _disc_ids(turma_id, disc_id) if disc_id else []
            conn = get_db()
            sql = "DELETE FROM planejamento WHERE turma_id = ? AND data_planejada = ?"
            params = [str(turma_id), data]
            if ids:
                sql += " AND disciplina_id IN (%s)" % ",".join("?" * len(ids))
                params += ids
            sql += " AND CAST(numero_aula AS INTEGER) = ?"
            params.append(int(aula))
            linhas = conn.execute(sql, params).rowcount
            conn.commit()
            conn.close()
        except Exception:
            linhas = 0

    if not removido and not linhas:
        return False, 0, "Nada foi removido."
    return removido, linhas, "ok"


def _hhmm(s) -> str:
    return re.sub(r"[^0-9]", "", str(s).split("às")[0].split("-")[0])[:4] or "0000"


def _norm_dia(s: str) -> str:
    import unicodedata
    if not s:
        return ""
    s = str(s).replace("ª", "a").replace("º", "o")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]", "", s.upper())


@st.cache_data(ttl=300, show_spinner=False)
def load_sabados_letivos():
    caminho = os.path.join(PROJECT_ROOT, "data", "calendario_letivo.json")
    try:
        with open(caminho, "r", encoding="utf-8") as fh:
            return json.load(fh).get("sabados_letivos", [])
    except Exception:
        return []


@st.cache_data(ttl=60, show_spinner=False)
def load_blacklist():
    caminho = os.path.join(PROJECT_ROOT, "data", "excecoes_alunos.json")
    try:
        with open(caminho, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def _feriados_config():
    """Calendário de feriados do `master_config` (chave `feriados.json`).

    Mesma fonte usada pelo gerador (`core/gerador.py`).
    """
    try:
        from tools import database_model
        return database_model.get_config("feriados.json", PROJECT_ROOT) or {}
    except Exception:
        return {}


def feriado_na_data(data_iso):
    """Descrição do feriado/recesso/exame para a data, ou '' se for dia letivo.

    Aceita `yyyy-mm-dd`, `dd/mm/aaaa` etc. (via `core_datas.parse_data`).
    Cobre as mesmas categorias do gerador: feriados, férias/recessos,
    planejamento/formação e exames.
    """
    d = core_datas.parse_data(data_iso)
    if not d:
        return ""
    iso = d.isoformat()
    cfg = _feriados_config() or {}
    for cat in ("feriados_e_datas_importantes", "ferias_e_recessos",
                "planejamento_e_formacao", "exames"):
        for item in cfg.get(cat, []) or []:
            if not isinstance(item, dict):
                continue
            desc = str(item.get("descricao") or "Feriado/recesso")
            if item.get("data") and str(item["data"]) == iso:
                return desc
            inicio, fim = item.get("inicio"), item.get("fim")
            if inicio and fim:
                try:
                    di = datetime.strptime(str(inicio)[:10], "%Y-%m-%d").date()
                    df = datetime.strptime(str(fim)[:10], "%Y-%m-%d").date()
                    if di <= d <= df:
                        return desc
                except Exception:
                    continue
    return ""


def parse_plano_txt(conteudo: str):
    meta = {}
    for chave in ("TURMA_ID", "DISCIPLINA_ID", "DATA", "HORARIO", "AULA_NUM", "DISCIPLINA_NOME"):
        m = re.search(rf"^{chave}:\s*(.+)$", conteudo, re.MULTILINE)
        if m:
            meta[chave] = m.group(1).strip()
    freq = []
    m = re.search(r"\[FREQUENCIA\](.*?)(?=\n\[|\Z)", conteudo, re.DOTALL)
    if m:
        for linha in m.group(1).splitlines():
            mm = re.match(r"-\s*(.+?):\s*(Presente|Falta)\s*$", linha.strip())
            if mm:
                freq.append({"Aluno": mm.group(1).strip(), "Status": mm.group(2)})
    return meta, freq


def resolver_mae(turma_code, disciplina_id):
    conn = get_db()
    try:
        cfg = conn.execute(
            "SELECT aliases_id, aliases_name FROM turma_disciplina_config WHERE turma_id = ? AND disciplina_id = ?",
            (turma_code, disciplina_id)).fetchone()
        if cfg and cfg["aliases_id"]:
            mae = conn.execute("SELECT id, name FROM subjects WHERE id = ?", (cfg["aliases_id"],)).fetchone()
            if mae:
                return int(mae["id"]), mae["name"]
            return int(cfg["aliases_id"]), cfg["aliases_name"]
    except Exception:
        pass
    finally:
        conn.close()
    return int(disciplina_id), None


def _disc_ids(turma_code, disciplina_id):
    """IDs equivalentes da disciplina (filha e base/alias)."""
    return core_banco.disc_ids(turma_code, disciplina_id)


def _data_dt(s):
    d = core_datas.parse_data(s)
    return datetime(d.year, d.month, d.day) if d else None


def _flash(msg, tipo="success"):
    """Guarda uma mensagem para exibir após o próximo `st.rerun()`."""
    st.session_state["_flash"] = (tipo, msg)


def _mostrar_flash():
    f = st.session_state.pop("_flash", None)
    if f:
        tipo, msg = f
        (st.success if tipo == "success" else st.warning)(msg)


@st.cache_data(ttl=60, show_spinner=False)
def load_slots(class_name: str, dia: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT day_of_week, time_slot, subject_name FROM weekly_schedule WHERE class_name = ?",
        (class_name,)).fetchall()
    conn.close()
    alvo = _norm_dia(dia)
    itens = [dict(r) for r in rows if _norm_dia(r["day_of_week"]) == alvo]
    return sorted(itens, key=lambda x: x["time_slot"])


_GENERICOS = {"DISCTEC"}


def _canon_disc(nome):
    try:
        from project_constants import SUBJECT_ALIASES, normalize_key
        nk = normalize_key(nome)
        return SUBJECT_ALIASES.get(str(nome).strip().upper(), SUBJECT_ALIASES.get(nk, nk))
    except Exception:
        return _norm_dia(nome)


def slots_da_disciplina(turma, subject, dia):
    alvo = _canon_disc(subject["name"])
    modular = str(subject.get("duration_type", "")).strip().lower() != "anual"
    out = []
    for s in load_slots(turma["name"], dia):
        c = _canon_disc(s.get("subject_name", ""))
        if c == alvo or (modular and c in _GENERICOS):
            out.append(s)
    return out


# ===========================================================================
# Geração de planos (local)
# ===========================================================================
def montar_conteudo_plano(turma, subject, data_iso, horario, n_aula, project_root):
    from tools import database_model
    from tools.plan_utils import build_plan_txt

    id_mae, nome_mae = resolver_mae(turma["code"], subject["id"])
    nome_mae = nome_mae or subject["name"]
    lesson = database_model.get_lesson_content_by_number(subject["id"], n_aula, project_root) or {}
    students = database_model.get_students_by_class_id(turma["code"], project_root)
    attendance_map, _src, _diag = core_banco.load_attendance_map_for(
        str(turma["code"]), id_mae, data_iso
    )
    txt = build_plan_txt(
        turma_id=str(turma["code"]), disc_id=str(id_mae), data=data_iso, horario=horario,
        aula_num=n_aula, disciplina_nome=nome_mae,
        lesson_title=lesson.get("title", ""),
        lesson_description=lesson.get("full_content") or lesson.get("description", ""),
        video_url=lesson.get("video_url", ""), students=students,
        attendance_map=attendance_map,
    )
    return txt, id_mae, nome_mae


def _salvar_plano(turma, subject, data_iso, horario, n_aula, project_root, destino="pendentes", tag=None):
    from tools import database_model
    txt, id_mae, nome_mae = montar_conteudo_plano(turma, subject, data_iso, horario, n_aula, project_root)
    if tag is None:
        tag = re.sub(r"[^0-9]", "", str(horario).split("-")[0])[:4] or "0000"
    nome_arquivo = f"plano_{turma['code']}_{id_mae}_{data_iso}_{tag}.txt"
    pasta = os.path.join(AULAS_DIR, destino)
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, nome_arquivo), "w", encoding="utf-8") as fh:
        fh.write(txt)
    database_model.save_planning([{
        "turma": turma["name"], "disciplina": nome_mae, "data": data_iso, "horario": horario,
        "numero_aula": n_aula, "status": "pendente", "turma_id": str(turma["code"]),
        "disciplina_id": subject["id"],
    }], project_root)
    return nome_arquivo, n_aula


def proximo_numero(turma, subject):
    ids = _disc_ids(turma["code"], subject["id"])
    nome = _nome_turma_atual(turma["code"])
    ph = ",".join("?" * len(ids))
    conn = get_db()
    reg = conn.execute(
        f"SELECT COUNT(*) FROM historico_aulas WHERE turma_id = ? AND disciplina_id IN ({ph}) AND turma = ?",
        (str(turma["code"]), *ids, nome)).fetchone()[0]
    plan = conn.execute(
        f"SELECT COUNT(*) FROM planejamento WHERE turma_id = ? AND disciplina_id IN ({ph})",
        (str(turma["code"]), *ids)).fetchone()[0]
    conn.close()
    return max(int(reg), int(plan)) + 1


def gerar_plano_reposicao(turma, subject, data_iso, horario, project_root):
    n = proximo_numero(turma, subject)
    return _salvar_plano(turma, subject, data_iso, horario, n, project_root)


def gerar_reposicao_dia(turma, subject, data_iso, ref_dia, project_root, max_aulas=4, horarios_abertos=False):
    slots = slots_da_disciplina(turma, subject, ref_dia)[:max_aulas]
    n = proximo_numero(turma, subject)
    gerados = []
    for i, s in enumerate(slots, 1):
        if horarios_abertos:
            horario, tag = "A DEFINIR", f"S{i}"
        else:
            horario, tag = s["time_slot"], None
        arq, _ = _salvar_plano(turma, subject, data_iso, horario, n, project_root, tag=tag)
        gerados.append(arq)
        n += 1
    return gerados


def renumerar_planejamento(turma, subject, project_root):
    id_mae, _ = resolver_mae(turma["code"], subject["id"])
    ids = _disc_ids(turma["code"], subject["id"])
    nome = _nome_turma_atual(turma["code"])
    ph = ",".join("?" * len(ids))
    conn = get_db()
    reg = conn.execute(
        f"SELECT COUNT(*) FROM historico_aulas WHERE turma_id = ? AND disciplina_id IN ({ph}) AND turma = ?",
        (str(turma["code"]), *ids, nome)).fetchone()[0]
    planos = [dict(r) for r in conn.execute(
        f"SELECT id, data_planejada, horario FROM planejamento WHERE turma_id = ? AND disciplina_id IN ({ph}) "
        "ORDER BY data_planejada, horario",
        (str(turma["code"]), *ids))]
    conn.close()

    n = int(reg) + 1
    contador_aberto = {}
    renumerados = []
    for p in planos:
        horario = p["horario"]
        txt, _, _ = montar_conteudo_plano(turma, subject, p["data_planejada"], horario, n, project_root)
        if re.search(r"\d", str(horario)):
            tag = re.sub(r"[^0-9]", "", str(horario).split("-")[0])[:4] or "0000"
        else:
            contador_aberto[p["data_planejada"]] = contador_aberto.get(p["data_planejada"], 0) + 1
            tag = f"S{contador_aberto[p['data_planejada']]}"
        nome_arquivo = f"plano_{turma['code']}_{id_mae}_{p['data_planejada']}_{tag}.txt"
        pasta = os.path.join(AULAS_DIR, "pendentes")
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, nome_arquivo), "w", encoding="utf-8") as fh:
            fh.write(txt)
        conn2 = get_db()
        conn2.execute("UPDATE planejamento SET numero_aula = ? WHERE id = ?", (n, p["id"]))
        conn2.commit()
        conn2.close()
        renumerados.append((p["data_planejada"], horario, n))
        n += 1
    return renumerados


def reconciliar(turma_code, disciplina_id):
    ids = _disc_ids(turma_code, disciplina_id)
    nome = _nome_turma_atual(turma_code)
    ph = ",".join("?" * len(ids))
    conn = get_db()
    hist = [dict(r) for r in conn.execute(
        f"SELECT data_aula, horario FROM historico_aulas WHERE turma_id = ? AND disciplina_id IN ({ph}) AND turma = ?",
        (str(turma_code), *ids, nome))]
    plan = [dict(r) for r in conn.execute(
        f"SELECT data_planejada, horario, numero_aula FROM planejamento WHERE turma_id = ? AND disciplina_id IN ({ph})",
        (str(turma_code), *ids))]
    conn.close()

    def _iso(d):
        try:
            return datetime.strptime(d, "%d/%m/%Y").strftime("%Y-%m-%d")
        except Exception:
            return d

    hist_keys = {(_iso(h["data_aula"]), _hhmm(h["horario"])) for h in hist}
    dias_portal = {k[0] for k in hist_keys}
    divergencias = []
    for p in plan:
        k = (p["data_planejada"], _hhmm(p["horario"]))
        if k not in hist_keys:
            sit = ("⚠️ Dia com aula no portal, mas horário diferente"
                   if p["data_planejada"] in dias_portal else "⬜ Sem registro no portal (a registrar)")
            divergencias.append({"Data": p["data_planejada"], "Horário (plano)": p["horario"],
                                 "Aula": p["numero_aula"], "Situação": sit})
    plan_keys = {(p["data_planejada"], _hhmm(p["horario"])) for p in plan}
    faltantes = [{"Data": _iso(h["data_aula"]), "Horário (portal)": h["horario"]}
                 for h in hist if (_iso(h["data_aula"]), _hhmm(h["horario"])) not in plan_keys]
    return divergencias, faltantes, len(hist), len(plan)


def _eh_reposicao_sabado(data_iso) -> bool:
    """Plano de reposição = data que cai em sábado."""
    d = core_datas.parse_data(data_iso)
    return bool(d) and d.weekday() == 5


def montar_html_impressao(grupos, titulo="Planos de Aula"):
    """Monta o HTML de impressão agrupando os planos.

    ``grupos``: lista de ``(subtitulo, [(nome, conteudo), ...])``.
    """
    blocos = []
    for subtitulo, itens in grupos:
        if not itens:
            continue
        blocos.append(f'<h2 class="grupo">{html.escape(subtitulo)} '
                      f'<span class="cont">({len(itens)})</span></h2>')
        for nome, conteudo in itens:
            blocos.append(f'<div class="plano"><h3>{html.escape(nome)}</h3>'
                          f'<pre>{html.escape(conteudo)}</pre></div>')
    return (
        "<!DOCTYPE html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(titulo)}</title>"
        "<style>body{font-family:Arial,sans-serif;margin:24px;}"
        ".grupo{font-size:16px;background:#333;color:#fff;padding:6px 10px;margin:20px 0 10px;}"
        ".grupo .cont{font-size:12px;font-weight:normal;opacity:.85;}"
        ".plano{page-break-after:always;}"
        "h3{font-size:14px;color:#333;border-bottom:1px solid #ccc;}"
        "pre{white-space:pre-wrap;font-family:'Courier New',monospace;font-size:12px;}"
        "</style></head><body>"
        f"<h1>{html.escape(titulo)}</h1>{''.join(blocos)}</body></html>"
    )


def calcular_gaps(inicio_iso: str, fim_iso: str):
    try:
        from tools import database_model
        rel = database_model.get_gap_analysis_report(PROJECT_ROOT, inicio_iso, fim_iso)
        if isinstance(rel, dict):
            return rel.get("gaps", []), rel.get("total_scheduled", 0)
        return rel, 0
    except Exception:
        return [], 0


# ===========================================================================
# Seções (render)
# ===========================================================================
def secao_painel(turma, subject):
    st.subheader("📊 Painel")
    if not subject:
        st.info("Selecione uma disciplina no sidebar.")
        return
    dados = panel_data(turma["code"], subject["id"])
    faltantes = max(0, int(dados["carga"]) - int(dados["registradas"]))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Carga prevista", f"{dados['carga']} aulas")
    m2.metric("Registradas (portal)", dados["registradas"])
    m3.metric("Planejadas (fila)", dados["planejadas"])
    m4.metric("Faltantes", faltantes)

    if dados["planejadas"] > int(dados["carga"]):
        st.error(f"⚠️ Há **{dados['planejadas']}** planos para uma carga de **{dados['carga']}** aulas "
                 f"(excedente de {dados['planejadas'] - int(dados['carga'])}). Veja a aba **⚙️ Config**.")

    if dados["ultima_data"]:
        st.info(f"📅 Última aula registrada no portal: **{dados['ultima_data']}**")
    else:
        st.info("Nenhuma aula registrada no portal para esta disciplina.")

    cA, cB = st.columns(2)
    with cA:
        with st.expander("📋 Histórico registrado (últimas 20)"):
            hist = listar_historico(turma["code"], subject["id"])[:20]
            if hist:
                st.dataframe(pd.DataFrame(hist), width="stretch", hide_index=True)
            else:
                st.caption("Sem registros.")
    with cB:
        with st.expander("🗓️ Fila de planejamento"):
            plan = listar_planejamento(turma["code"], subject["id"])
            if plan:
                for r in plan:
                    r["Feriado"] = feriado_na_data(r.get("data_planejada", "")) or ""
                st.dataframe(pd.DataFrame(plan), width="stretch", hide_index=True)
                n_fer = sum(1 for r in plan if r["Feriado"])
                if n_fer:
                    st.warning(f"⚠️ {n_fer} plano(s) na fila com data de feriado/recesso — registro bloqueado.")
            else:
                st.caption("Nada planejado ainda.")

    st.divider()
    st.markdown("#### 🕳️ Buracos (gaps) na grade")
    col_i, col_f = st.columns(2)
    with col_i:
        inicio = st.date_input("Início", value=date(2026, 2, 19), key="gap_ini")
    with col_f:
        fim = st.date_input("Fim", value=date.today(), key="gap_fim")
    if st.button("Calcular buracos", key="btn_gaps"):
        with st.spinner("Analisando..."):
            gaps, total = calcular_gaps(inicio.isoformat(), fim.isoformat())
        gaps_t = [g for g in gaps if str(g.get("turma_id")) == str(turma["code"])
                  and str(g.get("disciplina_id")) == str(subject["id"])]
        st.caption(f"{total} slots • {len(gaps)} buracos no período • {len(gaps_t)} nesta disciplina")
        if gaps_t:
            st.dataframe(pd.DataFrame(gaps_t), width="stretch", hide_index=True)
        else:
            st.success("Nenhum buraco.")


def secao_consolidadas(turma, subject):
    st.subheader("📈 Consolidadas — carga anual por turma")
    st.caption("Carga prevista × andamento do registro de todas as disciplinas. "
               "Registradas = portal | Prontas/Pendentes = `.txt` gerados | "
               "Faltantes = carga − (registradas + prontas + pendentes).")

    classes = load_classes()
    turmas_nome = ["Todas as turmas"] + [f"{c['name']} ({c['code']})" for c in classes]
    sel = st.selectbox("Turma:", turmas_nome, key="cons_turma")
    turma_filtro = None if sel == "Todas as turmas" else sel.split("(")[-1].rstrip(")")

    dados = consolidadas_data(turma_filtro)
    if not dados:
        st.info("Nenhuma disciplina encontrada.")
        return
    # Base = TODAS as disciplinas letivas (11 por turma, aliases agrupados;
    # vê `data/Turmas/Escola.txt`). O flag "ativa" só diz qual está em uso.
    base = dados

    tot_carga = sum(d["carga"] for d in base)
    tot_reg = sum(d["registradas"] for d in base)
    tot_prontas = sum(d["prontas"] for d in base)
    tot_pend = sum(d["pendentes"] for d in base)
    tot_falt = sum(d["faltantes"] for d in base)
    avanco = round(100 * tot_reg / tot_carga) if tot_carga else 0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Disciplinas", len(base))
    m2.metric("Carga anual", f"{tot_carga} aulas")
    m3.metric("Registradas", tot_reg)
    m4.metric("Prontas + pendentes", tot_prontas + tot_pend)
    m5.metric("Faltantes", tot_falt)
    st.progress(min(100, avanco), text=f"Avanço anual: **{avanco}%** da carga registrada")

    excedentes = [d for d in base if d["registradas"] + d["prontas"] + d["pendentes"] > d["carga"]]
    if excedentes:
        st.warning("⚠️ " + ", ".join(f"{d['disciplina']} ({d['turma_curta']})" for d in excedentes)
                   + " — combinado excede a carga prevista; veja a aba **⚙️ Config**.")

    # Gráfico 0 — janelas do fluxo letivo (Gantt por disciplina)
    rotulo_turma = sel == "Todas as turmas"
    jan_rows = []
    for d in base:
        if not d.get("janela_inicio") or not d.get("janela_fim"):
            continue
        escopo = "Anual" if (d["janela_fim"] - d["janela_inicio"]).days > 200 else "Mensal"
        jan_rows.append({
            "Disciplina": (f"{d['disciplina']} ({d['turma_curta']})" if rotulo_turma
                           else d["disciplina"]),
            "Inicio": d["janela_inicio"],
            "Fim": d["janela_fim"],
            "Escopo": escopo,
        })
    if jan_rows:
        st.markdown("#### 🗓️ Janela de cada disciplina no ano letivo")
        st.caption("`restricoes_planejamento` do calendário (via `disciplina_ids`); "
                   "a linha tracejada marca **hoje**.")
        df_jan = pd.DataFrame(jan_rows).sort_values("Inicio")
        ordenacao = df_jan["Disciplina"].tolist()
        barras = alt.Chart(df_jan).mark_bar(cornerRadius=3).encode(
            x=alt.X("Inicio:T", title="2026", scale=alt.Scale(
                domain=[df_jan["Inicio"].min(), df_jan["Fim"].max()])),
            x2="Fim:T",
            y=alt.Y("Disciplina:N", sort=ordenacao, title=None,
                    axis=alt.Axis(labelLimit=260, labelPadding=8)),
            color=alt.Color("Escopo:N", scale=alt.Scale(
                domain=["Anual", "Mensal"], range=["#2e7d32", "#1565c0"])),
            tooltip=[
                alt.Tooltip("Disciplina:N"),
                alt.Tooltip("Inicio:T", title="Início", format="%d/%m/%Y"),
                alt.Tooltip("Fim:T", title="Fim", format="%d/%m/%Y"),
                alt.Tooltip("Escopo:N"),
            ],
        )
        hoje = alt.Chart(pd.DataFrame({"d": [pd.Timestamp(datetime.now().date())]})) \
            .mark_rule(color="#d32f2f", strokeDash=[5, 4], size=2).encode(x="d:T")
        alt_h = max(420, 26 * len(df_jan) + 90)
        st.altair_chart(barras + hoje, width="stretch", height=alt_h)
    else:
        st.info("Nenhuma janela de disciplina encontrada no calendário letivo.")

    # Gráfico 1 — fluxo por disciplina (barras empilhadas)
    fluxo = []
    for d in base:
        disc = f"{d['disciplina']} ({d['turma_curta']})" if rotulo_turma else d["disciplina"]
        for etapa, qtd in (("Registradas", d["registradas"]), ("Prontas", d["prontas"]),
                           ("Pendentes", d["pendentes"]), ("Faltantes", d["faltantes"])):
            fluxo.append({"Disciplina": disc, "Etapa": etapa, "Aulas": qtd})
    st.markdown("#### 🧭 Fluxo das aulas por disciplina")
    st.bar_chart(pd.DataFrame(fluxo), x="Disciplina", y="Aulas", color="Etapa",
                 horizontal=True, stack=True, height=420)

    # Gráfico 2 — carga anual × registradas por turma
    st.markdown("#### 📚 Carga anual × registradas por turma")
    por_turma = {}
    for d in consolidadas_data(None):
        t = por_turma.setdefault(d["turma"], {"Carga anual": 0, "Registradas": 0})
        t["Carga anual"] += d["carga"]
        t["Registradas"] += d["registradas"]
    df_turma = pd.DataFrame([
        {"Turma": k, "Tipo": tipo, "Aulas": v[tipo]}
        for k, v in por_turma.items() for tipo in ("Carga anual", "Registradas")
    ])
    st.bar_chart(df_turma, x="Turma", y="Aulas", color="Tipo", height=320)

    # Tabela consolidada
    st.markdown("#### 📋 Detalhamento")
    tab = [{
        "Turma": d["turma_curta"],
        "Disciplina": d["disciplina"],
        "Ativa": "✅" if d["ativa"] else "⬜",
        "Janela": (f"{d['janela_inicio']:%d/%m} – {d['janela_fim']:%d/%m}"
                   if d.get("janela_inicio") and d.get("janela_fim") else "—"),
        "Carga": d["carga"],
        "Registradas": d["registradas"],
        "Prontas": d["prontas"],
        "Pendentes": d["pendentes"],
        "Fila": d["fila"],
        "Faltantes": d["faltantes"],
        "%": f"{round(100 * d['registradas'] / d['carga'])}%" if d["carga"] else "-",
    } for d in dados]
    st.dataframe(pd.DataFrame(tab), width="stretch", hide_index=True)


def secao_planos(turma, subject):
    st.subheader("📄 Planos (.txt)")
    if not subject:
        st.info("Selecione uma disciplina no sidebar.")
        return

    col_a, col_b = st.columns(2)
    with col_a:
        pasta = st.radio("Pasta:", ["prontas", "pendentes", "registradas"], horizontal=True, key="planos_pasta")
    with col_b:
        filtrar = st.checkbox("Filtrar pela turma/disciplina do sidebar", value=True, key="planos_filtrar")

    planos = listar_planos(pasta)
    if filtrar:
        ids = set(_disc_ids(turma["code"], subject["id"]))
        planos = [p for p in planos if p["turma_id"] == str(turma["code"]) and p["disciplina_id"] in ids]
    st.caption(f"{len(planos)} arquivo(s) em `aulas/{pasta}/`.")

    if planos:
        opcoes = {p["arquivo"]: p for p in planos}
        escolhido = st.selectbox("Visualizar plano:", list(opcoes.keys()), key="planos_sel")
        desc_fer = feriado_na_data(opcoes[escolhido].get("data", ""))
        if desc_fer:
            st.warning(f"⚠️ **Feriado/recesso**: `{opcoes[escolhido].get('data')}` — {desc_fer}. "
                       "O registro no portal está bloqueado para esta data.")
        conteudo = ler_plano_local(pasta, opcoes[escolhido]["arquivo"])
        st.text_area("Conteúdo", conteudo, height=320)

        col_d1, col_d2 = st.columns([0.35, 0.65])
        with col_d1:
            st.download_button("📥 Baixar este plano (.txt)", data=conteudo.encode("utf-8"),
                               file_name=opcoes[escolhido]["arquivo"], mime="text/plain",
                               width="stretch", key="dl_plano_unico")
        with col_d2:
            selecionados_zip = st.multiselect("Selecionar planos para ZIP (vazio = todos):",
                                              options=list(opcoes.keys()), key="zip_sel")
        itens_zip = selecionados_zip or list(opcoes.keys())
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for k in itens_zip:
                z.writestr(opcoes[k]["arquivo"], ler_plano_local(pasta, opcoes[k]["arquivo"]))
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.download_button(f"📦 Exportar {len(itens_zip)} em ZIP", data=buf.getvalue(),
                               file_name=f"planos_{pasta}.zip", mime="application/zip",
                               width="stretch", key="dl_zip")
        with col_e2:
            regulares, reposicoes = [], []
            for k in itens_zip:
                item = (k, ler_plano_local(pasta, opcoes[k]["arquivo"]))
                if _eh_reposicao_sabado(opcoes[k].get("data", "")):
                    reposicoes.append(item)
                else:
                    regulares.append(item)
            html_imp = montar_html_impressao(
                [("Aulas regulares", regulares), ("Reposições (sábados)", reposicoes)],
                titulo=f"Planos - {turma['name']}" + (f" / {subject['name']}" if subject else ""))
            st.download_button("🖨️ Exportar para impressão (.html)", data=html_imp.encode("utf-8"),
                               file_name="planos_impressao.html", mime="text/html",
                               width="stretch", key="dl_html")

        with st.expander("🗑️ Excluir plano selecionado"):
            st.caption("Remove o arquivo `.txt` e a linha correspondente em `planejamento`.")
            conf_del = st.checkbox("Confirmo a exclusão deste plano", key="planos_del_conf")
            if st.button("🗑️ Excluir este plano", disabled=not conf_del,
                         width="stretch", key="btn_del_plano"):
                ok, linhas, msg = excluir_plano(pasta, escolhido)
                if ok or linhas:
                    _flash(f"🗑️ Removido: arquivo={'sim' if ok else 'não'} • planejamento={linhas} linha(s).")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    _flash(msg, "warning")
    else:
        st.info("Nenhum plano nesta pasta com o filtro atual.")

    st.divider()
    st.markdown("#### ⚙️ Gerar planos (grade/calendário)")
    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        out_dir = st.radio("Destino:", ["pendentes", "prontas"], key="gerar_out")
    with col_g2:
        force = st.checkbox("Sobrescrever existentes", value=False, key="gerar_force")
    with col_g3:
        gerar = st.button("🚀 Gerar planos", type="primary", width="stretch", key="btn_gerar")

    col_e1, col_e2 = st.columns(2)
    opcoes_estrategia = _estrategias_disponiveis()
    sel_estrategia = col_e1.selectbox(
        "Estratégia da aula:",
        opcoes_estrategia,
        key="gerar_estrat",
        help="Tipo de estratégia aplicado aos planos gerados nesta rodada (seção [ESTRATEGIA]).",
    )
    col_e2.markdown(
        "**Tipos disponíveis:** " + " • ".join(opcoes_estrategia)
        if opcoes_estrategia else "",
        unsafe_allow_html=True,
    )

    col_r1, col_r2, col_r3 = st.columns(3)
    ativar_range = col_r1.checkbox("Limitar intervalo de aulas", value=False, key="gerar_range_on")
    aula_min = col_r2.number_input("De (aula nº)", min_value=1, value=1, key="gerar_range_min",
                                   disabled=not ativar_range)
    aula_max = col_r3.number_input("Até (aula nº)", min_value=1, value=40, key="gerar_range_max",
                                   disabled=not ativar_range)
    if ativar_range and aula_min > aula_max:
        st.warning("O intervalo está invertido: 'De' maior que 'Até'.")

    with st.expander("📝 Gerenciar lista de tipos de estratégia (uma por linha)"):
        texto_estr = st.text_area(
            "Tipos de estratégia", value="\n".join(opcoes_estrategia),
            height=110, key="gerar_estrat_lista",
        )
        if st.button("💾 Salvar lista de estratégias", key="btn_salvar_estrat"):
            nova = [x.strip() for x in texto_estr.splitlines() if x.strip()]
            if nova:
                _salvar_estrategias(nova)
                _flash(f"✅ Lista salva com {len(nova)} estratégia(s).")
            else:
                _flash("⚠️ Lista vazia — nada foi salvo.", "warning")
            st.cache_data.clear()
            st.rerun()

    if gerar:
        with st.spinner("Gerando planos..."):
            try:
                data = gerar_planos(
                    turma["code"], subject["id"], out_dir, force,
                    estrategia=sel_estrategia,
                    aula_min=(int(aula_min) if ativar_range and aula_min > 0 else None),
                    aula_max=(int(aula_max) if ativar_range and aula_max > 0 else None),
                )
                st.success(f"✅ {data.get('generated', 0)} plano(s) em `{data.get('path', out_dir)}`.")
                st.caption(
                    f"Frequência: {data.get('com_frequencia', 0)} plano(s) com lista"
                    + (f" • {data.get('freq_outra_disciplina', 0)} vindo de OUTRA disciplina"
                       if data.get('freq_outra_disciplina') else "")
                )
                st.json(data.get("debug", {}))
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Falha ao gerar: {e}")

    st.divider()
    st.markdown("#### 🔢 Renumerar em ordem de data")
    st.caption("Sequência normal (data/horário), continuando após o histórico. Reescreve AULA_NUM e conteúdo.")
    if st.button("🔢 Renumerar planos pendentes", key="btn_renumerar"):
        with st.spinner("Renumerando..."):
            try:
                res = renumerar_planejamento(turma, subject, PROJECT_ROOT)
                st.success(f"✅ {len(res)} plano(s) renumerado(s).")
                st.dataframe(pd.DataFrame(res, columns=["Data", "Horário", "AULA_NUM"]),
                             width="stretch", hide_index=True)
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Falha ao renumerar: {e}")


def secao_individual(turma, subject):
    st.subheader("👁️ Plano individual")
    if not subject:
        st.info("Selecione uma disciplina no sidebar.")
        return
    bl = load_blacklist()
    bl_nomes = {str(n).upper() for n in bl.get("blacklist_names", [])}

    pasta = st.radio("Pasta:", ["pendentes", "prontas", "registradas"], horizontal=True, key="ind_pasta")
    _ids_ind = set(_disc_ids(turma["code"], subject["id"]))
    planos = [p for p in listar_planos(pasta)
              if p["turma_id"] == str(turma["code"]) and p["disciplina_id"] in _ids_ind]
    if not planos:
        st.info("Nenhum plano encontrado.")
        return

    opcoes = {p["arquivo"]: p for p in planos}
    sel = st.selectbox("Plano:", list(opcoes.keys()), key="ind_sel")
    conteudo = ler_plano_local(pasta, sel)
    meta, freq = parse_plano_txt(conteudo)

    desc_fer = feriado_na_data(opcoes[sel].get("data", "") or meta.get("DATA", ""))
    if desc_fer:
        st.warning(f"⚠️ **Feriado/recesso**: `{opcoes[sel].get('data')}` — {desc_fer}. "
                   "Registro no portal bloqueado para esta data.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Data", meta.get("DATA", "-"))
    c2.metric("Horário", meta.get("HORARIO", "-"))
    c3.metric("Aula", meta.get("AULA_NUM", "-"))
    c4.metric("Disciplina", meta.get("DISCIPLINA_NOME", "-")[:26])
    st.caption(f"TURMA_ID {meta.get('TURMA_ID', '-')} • DISCIPLINA_ID {meta.get('DISCIPLINA_ID', '-')} • `{sel}`")

    # Frequência ao vivo (banco) x plano congelado (.txt)
    st.markdown("#### 🔎 Frequência ao vivo (banco)")
    try:
        _p_info = opcoes[sel]
        mapa_vivo, fonte_vivo, diag_vivo = core_banco.load_attendance_map_for(
            str(_p_info.get("turma_id") or meta.get("TURMA_ID")),
            str(_p_info.get("disciplina_id") or meta.get("DISCIPLINA_ID")),
            str(_p_info.get("data") or meta.get("DATA")),
        )
    except Exception as e:
        mapa_vivo, fonte_vivo = {}, None
        diag_vivo = {"encontrou": False, "quantidade": 0, "fontes": [], "erro": str(e)}
    if diag_vivo.get("excecao"):
        st.info(f"ℹ️ Exceção manual: {diag_vivo['excecao']}")
    if diag_vivo.get("encontrou"):
        if diag_vivo.get("outra_disciplina"):
            st.warning(f"⚠️ Frequência de **outra disciplina** — {fonte_vivo} — "
                       f"{diag_vivo['quantidade']} aluno(s). Conferir antes de registrar.")
        else:
            st.success(f"✅ Frequência encontrada ({diag_vivo['quantidade']} aluno(s)) — "
                       f"fonte: {fonte_vivo}.")
        with st.expander(f"📋 Frequência ao vivo — {diag_vivo['quantidade']} aluno(s)"):
            linhas_vivo = [{"Aluno": k, "Status": v} for k, v in sorted(mapa_vivo.items())]
            st.dataframe(pd.DataFrame(linhas_vivo), width="stretch", hide_index=True, height=260)
        if freq:
            st.caption(f"Frequência congelada no .txt: {len(freq)} aluno(s) • "
                       f"ao vivo: {diag_vivo['quantidade']}.")
    else:
        consultadas = ", ".join(diag_vivo.get("fontes") or []) or \
            "tabela attendance + JSONs do plugin"
        st.warning(f"⚠️ Nenhuma frequência encontrada para esta aula. "
                   f"Consultados: {consultadas}. Alunos fora do mapa entram como "
                   "'Presente' no .txt.")

    col_f1, col_f2 = st.columns([0.55, 0.45])
    with col_f1:
        st.markdown("##### 👥 Frequência")
        if freq:
            presentes = sum(1 for f in freq if f["Status"] == "Presente")
            faltas = sum(1 for f in freq if f["Status"] == "Falta")
            mm1, mm2, mm3 = st.columns(3)
            mm1.metric("Alunos", len(freq)); mm2.metric("Presentes", presentes); mm3.metric("Faltas", faltas)
            df = pd.DataFrame(freq)
            df["Na lista negra"] = df["Aluno"].apply(lambda n: "🚫" if n.upper() in bl_nomes else "")
            st.dataframe(df, width="stretch", hide_index=True, height=340)
        else:
            st.caption("Sem lista de frequência.")
    with col_f2:
        st.markdown("##### 🚫 Lista negra")
        st.caption("`blacklist`/`blacklist_names` sempre **Falta**; `dropouts` são omitidos.")
        if bl:
            st.write("**Faltas (RA):**", ", ".join(bl.get("blacklist", [])) or "—")
            st.write("**Faltas (nome):**")
            for n in bl.get("blacklist_names", []):
                st.write(f"- {n}")
            st.write("**Dropouts:**", ", ".join(bl.get("dropouts", [])) or "—")
        else:
            st.caption("`data/excecoes_alunos.json` não encontrado.")

    with st.expander("📄 Conteúdo completo", expanded=True):
        st.text(conteudo)
    st.download_button("📥 Baixar este plano (.txt)", data=conteudo.encode("utf-8"),
                       file_name=sel, mime="text/plain", key="dl_ind")


def secao_reconciliacao(turma, subject):
    st.subheader("🔍 Reconciliação: portal × planejamento")
    if not subject:
        st.info("Selecione uma disciplina no sidebar.")
        return
    div, falt, n_hist, n_plan = reconciliar(turma["code"], subject["id"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Aulas no portal", n_hist); c2.metric("Planos", n_plan); c3.metric("Divergências", len(div))
    st.caption("Divergência = plano cujo par (data, horário) **não** existe no portal.")
    if div:
        st.warning(f"⚠️ {len(div)} plano(s) divergente(s).")
        st.dataframe(pd.DataFrame(div), width="stretch", hide_index=True)
    else:
        st.success("Nenhuma divergência.")
    with st.expander(f"⬜ Aulas no portal sem plano ({len(falt)})"):
        if falt:
            st.dataframe(pd.DataFrame(falt), width="stretch", hide_index=True)
        else:
            st.caption("Todas têm plano.")


def secao_sabados(turma, subject):
    st.subheader("🟣 Sábados letivos / reposição")
    st.caption("Usa `data/calendario_letivo.json`; horário do **dia equivalente**. Máx. **4 aulas** por sábado.")
    sabados = load_sabados_letivos()
    if not sabados:
        st.info("Nenhum sábado letivo configurado.")
        return

    linhas = []
    for sat in sabados:
        d_iso = sat.get("data_iso")
        if not d_iso and sat.get("data"):
            try:
                d_iso = datetime.strptime(sat["data"], "%d/%m/%Y").strftime("%Y-%m-%d")
            except Exception:
                d_iso = ""
        status = status_sabado(d_iso, turma["code"], subject["id"]) if (d_iso and subject) else "-"
        linhas.append({"Data": d_iso, "Tipo": sat.get("tipo", ""), "Dia equivalente": sat.get("dia_equivalente", ""),
                       "Descrição": sat.get("descricao", ""), "Status": status})
    st.dataframe(pd.DataFrame(linhas), width="stretch", hide_index=True)

    st.divider()
    st.markdown("#### ➕ Gerar plano de reposição (escolhendo o dia de referência)")
    if not subject:
        st.info("Selecione uma disciplina no sidebar.")
        return

    datas_sab = [l["Data"] for l in linhas if l["Data"]]
    c1, c2, c3 = st.columns(3)
    with c1:
        sat_sel = st.selectbox("Sábado:", datas_sab, key="sat_data")
    with c2:
        ref_padrao = next((l["Dia equivalente"] for l in linhas if l["Data"] == sat_sel), "Segunda")
        dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta"]
        idx = next((i for i, d in enumerate(dias) if _norm_dia(d) == _norm_dia(ref_padrao)), 0)
        ref_dia = st.selectbox("Dia de referência (grade):", dias, index=idx, key="sat_ref")
    with c3:
        slots = slots_da_disciplina(turma, subject, ref_dia)
        opcoes_h = [s["time_slot"] for s in slots]
        horario_sel = st.selectbox("Horário:", opcoes_h, key="sat_horario") if opcoes_h else None
        if not opcoes_h:
            st.warning("Sem slots da disciplina nesse dia.")

    st.caption(f"Slots da **disciplina** em {ref_dia}: **{len(slots)}** "
               f"({', '.join(opcoes_h) if opcoes_h else 'nenhum'}) • sábado: máx. 4 aulas")
    abertos = st.checkbox("Horários em aberto (A DEFINIR)", value=False, key="sat_abertos",
                          help="Gera com HORARIO 'A DEFINIR' (S1..S4) para o portal decidir.")

    cbtn1, cbtn2 = st.columns(2)
    with cbtn1:
        if horario_sel and st.button("➕ Gerar plano deste horário", key="btn_gerar_rep"):
            with st.spinner("Gerando..."):
                try:
                    arq, n = gerar_plano_reposicao(turma, subject, sat_sel, horario_sel, PROJECT_ROOT)
                    st.success(f"✅ `aulas/pendentes/{arq}` (AULA_NUM {n:02d}).")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Falha: {e}")
    with cbtn2:
        if slots and st.button(f"➕ Gerar até 4 planos ({ref_dia})", type="primary", key="btn_gerar_rep_dia"):
            with st.spinner("Gerando..."):
                try:
                    gerados = gerar_reposicao_dia(turma, subject, sat_sel, ref_dia, PROJECT_ROOT,
                                                  max_aulas=4, horarios_abertos=abertos)
                    st.success(f"✅ {len(gerados)} plano(s) gerado(s).")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Falha: {e}")

    st.divider()
    st.markdown("#### 🗑️ Excluir planos de reposição do sábado")
    st.caption("Se gerou na data errada, remova aqui: apaga o `.txt` e a linha do `planejamento`.")
    ids_sat = set(_disc_ids(turma["code"], subject["id"]))
    itens_sat = []
    for sub in ("pendentes", "prontas", "registradas"):
        for p in listar_planos(sub):
            if (p["data"] == sat_sel and p["turma_id"] == str(turma["code"])
                    and p["disciplina_id"] in ids_sat):
                itens_sat.append((sub, p["arquivo"]))
    if not itens_sat:
        st.caption(f"Nenhum plano encontrado para {sat_sel}.")
    else:
        rotulos = [f"{sub}/{arq}" for sub, arq in itens_sat]
        sel_del = st.multiselect(f"{len(rotulos)} plano(s) em {sat_sel} — selecione para excluir:",
                                 rotulos, key="sat_del_sel")
        conf_del = st.checkbox("Confirmo a exclusão", key="sat_del_conf")
        if st.button("🗑️ Excluir selecionados", type="primary",
                     disabled=not (sel_del and conf_del), key="btn_del_sat"):
            n_arq = n_linhas = 0
            for rot in sel_del:
                sub, arq = rot.split("/", 1)
                ok, linhas, _ = excluir_plano(sub, arq)
                n_arq += 1 if ok else 0
                n_linhas += linhas
            _flash(f"🗑️ {n_arq} arquivo(s) e {n_linhas} linha(s) do planejamento removidos.")
            st.cache_data.clear()
            st.rerun()


def status_sabado(data_iso, turma_code, disciplina_id):
    try:
        d_dmy = datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        d_dmy = data_iso
    ids = _disc_ids(turma_code, disciplina_id)
    nome = _nome_turma_atual(turma_code)
    ph = ",".join("?" * len(ids))
    conn = get_db()
    try:
        reg = conn.execute(
            f"SELECT 1 FROM historico_aulas WHERE data_aula = ? AND turma_id = ? AND disciplina_id IN ({ph}) "
            "AND turma = ? LIMIT 1",
            (d_dmy, str(turma_code), *ids, nome)).fetchone()
        plan = conn.execute(
            f"SELECT 1 FROM planejamento WHERE data_planejada = ? AND turma_id = ? AND disciplina_id IN ({ph}) LIMIT 1",
            (data_iso, str(turma_code), *ids)).fetchone()
    except Exception:
        reg = plan = None
    conn.close()
    if reg:
        return "✅ Registrada"
    if plan:
        return "🟦 Planejada"
    prefixos = [f"plano_{turma_code}_{did}_{data_iso}" for did in ids]
    for sub in ("prontas", "pendentes", "registradas"):
        folder = os.path.join(AULAS_DIR, sub)
        if os.path.isdir(folder) and any(f.startswith(tuple(prefixos)) for f in os.listdir(folder)):
            return "📄 Plano gerado"
    return "⬜ Ausente"


def secao_registrar(turma, subject):
    st.subheader("🤖 Registrar / Sincronizar")
    prontos = listar_planos("prontas")
    if subject:
        _ids_reg = set(_disc_ids(turma["code"], subject["id"]))
        prontos = [p for p in prontos if p["turma_id"] == str(turma["code"]) and p["disciplina_id"] in _ids_reg]

    # Bloqueio: planos com data de feriado/recesso não vão para o portal
    livres, bloqueados = [], []
    for p in prontos:
        desc = feriado_na_data(p.get("data", ""))
        if desc:
            bloqueados.append((p, desc))
        else:
            livres.append(p)
    if bloqueados:
        detalhe = ", ".join(f"`{p['arquivo']}` ({d})" for p, d in bloqueados)
        st.warning(
            f"⚠️ **{len(bloqueados)} plano(s) em data de feriado** — registro bloqueado: {detalhe}. "
            "Gere novamente o planejamento (o gerador agora pula feriados) ou exclua o plano."
        )

    selecionados = st.multiselect("Planos prontos para registrar:", options=[p["arquivo"] for p in livres], key="reg_sel")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("▶️ Registrar selecionados", type="primary", width="stretch",
                     disabled=not selecionados, key="btn_reg_sel"):
            ok, msg = registrar_planos(files=selecionados); (st.success if ok else st.error)(msg)
    with c2:
        if st.button("▶️ Registrar TODOS os prontos", width="stretch", key="btn_reg_all",
                     disabled=not livres):
            ok, msg = registrar_planos(files=[p["arquivo"] for p in livres]); (st.success if ok else st.error)(msg)
    with c3:
        if st.button("🔄 Sincronizar (raspagem)", width="stretch", key="btn_raspagem"):
            ok, msg = rodar_raspagem(); (st.success if ok else st.error)(msg)

    st.divider()
    st.markdown("#### 📈 Progresso do robô")
    if st.button("Atualizar status", key="btn_status"):
        st.rerun()
    s = ler_registro_status()
    if s:
        total = int(s.get("total", 0) or 0); proc = int(s.get("processados", 0) or 0)
        st.progress((proc / total) if total else 0.0)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Status", s.get("status", "-")); c2.metric("Processados", f"{proc}/{total}")
        c3.metric("Sucessos", s.get("sucessos", 0)); c4.metric("Falhas", s.get("falhas", 0))
        if s.get("aula_atual"):
            st.caption(f"Aula atual: `{s['aula_atual']}`")
        det = s.get("detalhes") or []
        if det:
            st.dataframe(pd.DataFrame(det), width="stretch", hide_index=True)
    else:
        st.caption("Sem status. O robô escreve em `data/logs/registro_status.json`.")
    st.caption("Pré-requisitos: `pip install selenium webdriver-manager` e `data/credentials.json`.")


def secao_config(turma, subject):
    st.subheader("⚙️ Configurações e manutenção")

    # 0) Feriados (master_config -> feriados.json)
    st.markdown("#### 📅 Feriados (`master_config` → `feriados.json`)")
    cfg_fer = _feriados_config()
    if not cfg_fer:
        st.warning("Nenhum calendário de feriados encontrado na `master_config` "
                   "(chave `feriados.json`).")
    else:
        _CATS = (
            ("feriados_e_datas_importantes", "Feriados"),
            ("ferias_e_recessos", "Férias/Recessos"),
            ("planejamento_e_formacao", "Planejamento/Formação"),
            ("exames", "Exames"),
        )
        linhas_fer = []
        n_datas = 0
        for cat, rotulo in _CATS:
            for item in cfg_fer.get(cat, []) or []:
                if not isinstance(item, dict):
                    continue
                desc = str(item.get("descricao") or "")
                if item.get("data"):
                    linhas_fer.append({"Categoria": rotulo, "Início": item["data"],
                                       "Fim": item["data"], "Descrição": desc})
                    n_datas += 1
                elif item.get("inicio") and item.get("fim"):
                    linhas_fer.append({"Categoria": rotulo, "Início": item["inicio"],
                                       "Fim": item["fim"], "Descrição": desc})
                    try:
                        di = datetime.strptime(str(item["inicio"])[:10], "%Y-%m-%d").date()
                        df = datetime.strptime(str(item["fim"])[:10], "%Y-%m-%d").date()
                        n_datas += (df - di).days + 1
                    except Exception:
                        pass
        col_f1, col_f2 = st.columns([0.58, 0.42])
        with col_f1:
            if linhas_fer:
                st.dataframe(pd.DataFrame(linhas_fer), width="stretch",
                             hide_index=True, height=260)
            else:
                st.caption("Calendário sem períodos cadastrados.")
            st.caption(f"**{len(linhas_fer)}** período(s)/data(s) • **{n_datas}** dia(s) "
                       "não letivo(s) • fonte: tabela `master_config`.")
        with col_f2:
            data_chk = st.date_input("Verificar data", value=date.today(),
                                     key="cfg_fer_chk")
            desc_chk = feriado_na_data(data_chk.isoformat())
            if desc_chk:
                st.warning(f"⚠️ `{data_chk.isoformat()}` **não é dia letivo**: {desc_chk}. "
                           "Geração e registro de aulas bloqueados nesta data.")
            else:
                st.success(f"✅ `{data_chk.isoformat()}` é dia letivo "
                           "(não consta no calendário de feriados).")

    # 1) Monitor de limite
    st.markdown("#### 📊 Monitor de limite (planos × carga horária)")
    limite = monitor_limite()
    if limite:
        df = pd.DataFrame(limite)[["turma_id", "disciplina_id", "Disciplina", "Planos", "Limite", "Excedente", "Excede"]]
        st.dataframe(df, width="stretch", hide_index=True)
        excedentes = [r for r in limite if r["Excede"]]
        if excedentes:
            st.error(f"⚠️ {len(excedentes)} disciplina(s) com planos acima da carga horária. "
                     f"Total excedente: {sum(r['Excedente'] for r in excedentes)}.")
        else:
            st.success("Nenhuma disciplina excede a carga horária.")
    else:
        st.info("Tabela `planejamento` vazia.")

    # 2) Registros suspeitos
    sus = planejamento_suspeitos()
    st.markdown("#### 🧨 Registros suspeitos")
    if sus:
        st.error(f"⚠️ {len(sus)} registro(s) com `turma_id`/`disciplina_id` inválidos.")
        st.dataframe(pd.DataFrame(sus), width="stretch", hide_index=True)
        if st.button("🗑️ Remover registros suspeitos", key="btn_rem_sus"):
            n = remover_suspeitos()
            st.success(f"{n} registro(s) removido(s).")
            st.cache_data.clear()
            st.rerun()
    else:
        st.success("Nenhum registro suspeito.")

    # 3) Data de corte
    st.markdown("#### 📅 Data de corte do planejamento")
    corte_atual = get_config("data_corte_planejamento", "2026-05-01")
    try:
        corte_dt = datetime.strptime(str(corte_atual)[:10], "%Y-%m-%d").date()
    except Exception:
        corte_dt = date(2026, 5, 1)
    st.caption(f"Atual: `{corte_atual}` — o gerador ignora aulas anteriores a esta data.")
    nova = st.date_input("Nova data de corte", value=corte_dt, key="cfg_corte")
    if st.button("💾 Salvar data de corte", key="btn_corte"):
        set_config("data_corte_planejamento", nova.isoformat())
        st.success(f"Data de corte atualizada para {nova.isoformat()}.")
        st.cache_data.clear()

    # 4) Reset do planejamento
    st.markdown("#### 🧹 Resetar tabela `planejamento`")
    st.warning("Ações destrutivas. Não removem os arquivos .txt em `aulas/`.")
    escopo = st.radio("Escopo:", ["Tudo", "Somente esta turma", "Somente esta turma/disciplina"], key="cfg_escopo")
    confirmar = st.checkbox("Confirmo que quero apagar", key="cfg_conf")
    if st.button("🗑️ Apagar planejamento", disabled=not confirmar, key="btn_reset"):
        if escopo == "Tudo":
            n = reset_planejamento()
        elif escopo == "Somente esta turma":
            n = reset_planejamento(turma_id=turma["code"])
        else:
            n = reset_planejamento(turma_id=turma["code"], disciplina_id=subject["id"] if subject else None)
        st.success(f"{n} registro(s) removido(s) do planejamento.")
        st.cache_data.clear()
        st.rerun()

    # 5) Outros parâmetros
    st.divider()
    st.markdown("#### 🔧 Outros parâmetros (`master_config`)")
    cfgs = core_banco.listar_parametros()
    if cfgs:
        st.dataframe(pd.DataFrame(cfgs), width="stretch", hide_index=True)
    else:
        st.caption("Nenhum parâmetro cadastrado (as chaves `.json` de calendário/"
                   "feriados ficam fora desta lista).")
    with st.form("cfg_novo"):
        c1, c2 = st.columns([0.4, 0.6])
        with c1:
            chave = st.text_input("Chave")
        with c2:
            valor = st.text_input("Valor")
        if st.form_submit_button("Salvar parâmetro") and chave:
            set_config(chave, valor)
            st.success(f"`{chave}` = `{valor}`")
            st.cache_data.clear()


# ===========================================================================
# Sidebar (contexto + navegação)
# ===========================================================================
classes = load_classes()
if not classes:
    st.error("Nenhuma turma encontrada em `escola_ativa.db`.")
    st.stop()

with st.sidebar:
    st.markdown("### 🗂️ Planejamento e Registro")

    nomes_turma = [f"{c['name']} ({c['code']})" for c in classes]
    turma_sel = st.selectbox("Turma", nomes_turma, key="sb_turma")
    turma = classes[nomes_turma.index(turma_sel)]

    subs = load_subjects_for_class(turma["id"])
    sub_map = {s["name"]: s for s in subs}
    sub_sel = st.selectbox("Disciplina", list(sub_map.keys()) if sub_map else ["(sem disciplinas)"], key="sb_sub")
    subject = sub_map.get(sub_sel)

    st.divider()
    pagina = st.radio("Navegação", [
        "📊 Painel",
        "📈 Consolidadas",
        "📄 Planos",
        "👁️ Plano Individual",
        "🔍 Reconciliação",
        "🟣 Sábados (reposição)",
        "🤖 Registrar / Sincronizar",
        "⚙️ Config",
    ], key="sb_nav")

    st.divider()
    if st.button("🔄 Recarregar dados", width="stretch", key="sb_reload"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Banco: `{os.path.relpath(DB_PATH, PROJECT_ROOT)}`")

st.title("🗂️ Planejamento e Registro de Aulas")
_mostrar_flash()

_SECOES = {
    "📊 Painel": secao_painel,
    "📈 Consolidadas": secao_consolidadas,
    "📄 Planos": secao_planos,
    "👁️ Plano Individual": secao_individual,
    "🔍 Reconciliação": secao_reconciliacao,
    "🟣 Sábados (reposição)": secao_sabados,
    "🤖 Registrar / Sincronizar": secao_registrar,
    "⚙️ Config": secao_config,
}
_render = _SECOES.get(pagina)
if _render:
    _render(turma, subject)
