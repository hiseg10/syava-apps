"""Acesso ao banco SQLite local e utilidades de apoio do planejamento.

Sem dependência de FastAPI: pode ser importado pelo app Streamlit e pela API.
"""

import os
import sys
import json
import re
import sqlite3
import unicodedata

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(CORE_DIR)                        # apps/planejamento_registro
PROJECT_ROOT = os.path.dirname(os.path.dirname(APP_DIR))   # SysAva
API_DIR = os.path.join(PROJECT_ROOT, "apps", "api")

for _p in (PROJECT_ROOT, API_DIR, os.path.join(API_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

AULAS_DIR = os.path.join(PROJECT_ROOT, "aulas")

# O banco pode estar em locais diferentes dependendo da configuração
POSSIBLE_DB_PATHS = [
    os.path.join(PROJECT_ROOT, "data", "escola_ativa.db"),
    os.path.join(PROJECT_ROOT, "escola_ativa.db"),
    os.path.join(PROJECT_ROOT, "data", "automacao", "escola_ativa.db"),
    os.path.join(PROJECT_ROOT, "backend", "data", "escola_ativa.db"),
]

DB_PATH = next((p for p in POSSIBLE_DB_PATHS if os.path.exists(p)), POSSIBLE_DB_PATHS[0])


# ---------------------------------------------------------------------------
# Conexão
# ---------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


# Mantém compatibilidade com o nome usado pela API
get_db_connection = get_db


# ---------------------------------------------------------------------------
# Configuração (tabela master_config; antes planejamento_config)
# ---------------------------------------------------------------------------
def _database_model():
    try:
        from tools import database_model
    except ImportError:
        import database_model
    return database_model


def get_config(chave, default=None):
    """Lê uma configuração da tabela ``master_config`` (valor em JSON)."""
    try:
        val = _database_model().get_config(chave, PROJECT_ROOT)
    except Exception:
        val = None
    return default if val is None else val


def set_config(chave, valor):
    """Grava uma configuração na tabela ``master_config`` (valor em JSON)."""
    _database_model().set_config(chave, valor, PROJECT_ROOT)


def listar_parametros():
    """Chaves de parâmetros da ``master_config`` (ignora os ``.json`` grandes)."""
    conn = get_db()
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(master_config)")]
        if 'key' in cols:
            rows = conn.execute(
                "SELECT key, value, updated_at FROM master_config ORDER BY key"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT chave, valor, NULL FROM master_config ORDER BY chave"
            ).fetchall()
        out = []
        for r in rows:
            if str(r[0]).endswith(".json"):
                continue
            out.append({"chave": r[0], "valor": r[1], "atualizado": r[2] or ""})
        return out
    except Exception:
        return []
    finally:
        conn.close()


def del_config(chave):
    """Remove uma configuração da ``master_config`` (recusa chaves ``.json``)."""
    chave = str(chave).strip()
    if not chave:
        raise ValueError("Chave vazia.")
    if chave.endswith(".json"):
        raise ValueError("Chaves `.json` (calendário/feriados) não podem ser excluídas.")
    conn = get_db()
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(master_config)")]
        if 'key' in cols:
            conn.execute("DELETE FROM master_config WHERE key = ?", (chave,))
        else:
            conn.execute("DELETE FROM master_config WHERE chave = ?", (chave,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# IDs equivalentes de disciplina (filha <-> base/alias)
# ---------------------------------------------------------------------------
def disc_ids(turma_code, disciplina_id):
    """IDs equivalentes da disciplina conforme ``turma_disciplina_config``.

    O histórico é gravado com o ID base (ex.: 6) e os planos com o ID da turma
    (ex.: 33/34). Consultas precisam cobrir os dois lados.
    """
    ids = {str(disciplina_id)}
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT disciplina_id, aliases_id FROM turma_disciplina_config WHERE turma_id = ?",
            (turma_code,),
        ).fetchall()
        conn.close()
        for r in rows:
            did, al = str(r["disciplina_id"]), r["aliases_id"]
            if al is None:
                continue
            al = str(al)
            if did in ids or al in ids:
                ids.add(did)
                ids.add(al)
    except Exception:
        pass
    return sorted(ids)


# ---------------------------------------------------------------------------
# Frequência (tabela `attendance` do banco + arquivos JSON do plugin)
# ---------------------------------------------------------------------------
ATTENDANCE_FILES_PRIORITY = [
    "student_attendance_corrigido.json",
    "student_attendance_normalized.json",
    "student_attendance.json",
    "student_attendance_planned.json",
]

# Pastas onde o plugin grava a frequência — o local atual é data/repo/plugins;
# api/plugins é mantido por compatibilidade com instalações antigas.
ATTENDANCE_JSON_LOCATIONS = [
    os.path.join(PROJECT_ROOT, "data", "repo", "plugins"),
    os.path.join(PROJECT_ROOT, "api", "plugins"),
]

_attendance_cache = {}


def _norm_key(s):
    """Normaliza string p/ comparação: minúsculas, sem acento e sem pontuação."""
    try:
        s = unicodedata.normalize("NFKD", str(s or ""))
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        return "".join(ch for ch in s.lower() if ch.isalnum())
    except Exception:
        return str(s or "").strip().lower()


def load_attendance_json(att_name):
    """Carrega (com cache) um arquivo de frequência da pasta de plugins.

    Procura em data/repo/plugins (local atual) e depois em api/plugins.
    """
    if att_name in _attendance_cache:
        return _attendance_cache[att_name]
    data = {}
    for folder in ATTENDANCE_JSON_LOCATIONS:
        att_file = os.path.join(folder, att_name)
        if os.path.exists(att_file):
            try:
                with open(att_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    data = {}
            except Exception:
                data = {}
            break
    _attendance_cache[att_name] = data
    return data


def load_attendance_from_db(turma_id, data_iso, disc_id=None, permitir_outra=True):
    """Lê a frequência real da tabela `attendance` do banco local (data exata).

    Resolução estruturada como: DATA -> TURMA -> DISCIPLINA.
      1. Filtra pela data exata da aula (data);
      2. Casa a turma por nome normalizado (turma);
      3. Filtra pela disciplina (`subject_id`) quando há registros com a
         disciplina preenchida. Linhas legadas (subject_id NULL) são usadas
         apenas como fallback, pois não é possível atribuí-las a uma matéria.
      4. Fallback opcional: se a turma tem frequência na data porém gravada sob
         OUTRA disciplina, usa o mapa maior e sinaliza em ``extra``.

    Retorna ``(mapa, origem, extra)``; ``extra`` pode conter
    ``outra_disciplina``, ``disciplina`` e ``disciplina_nome``.
    """
    try:
        conn = get_db()
        norm_classes = []
        for r in conn.execute("SELECT id, code, name FROM classes").fetchall():
            if str(r["id"]) == str(turma_id) or str(r["code"]) == str(turma_id):
                n = _norm_key(r["name"])
                if n:
                    norm_classes.append(n)
        if not norm_classes:
            conn.close()
            return None, None, {}
        rows = conn.execute(
            "SELECT student_name, is_present, class_name, subject_id FROM attendance WHERE date = ?",
            (data_iso,),
        ).fetchall()
    except Exception:
        return None, None, {}

    disc = str(disc_id) if disc_id is not None else None
    mapa_exata = {}
    mapa_legado = {}
    por_disciplina = {}
    for r in rows:
        cnc = _norm_key(r["class_name"])
        if not cnc:
            continue
        if not any(nc in cnc or cnc in nc for nc in norm_classes):
            continue
        is_pres = str(r["is_present"] or "").strip().lower()
        status = "Presente" if is_pres in ("1", "true", "presente", "sim") else "Falta"
        key = str(r["student_name"]).upper().strip()
        sid = r["subject_id"]
        if disc is None or sid is None:
            mapa_legado[key] = status
        elif str(sid) == disc:
            mapa_exata[key] = status
        else:
            por_disciplina.setdefault(str(sid), {})[key] = status

    if mapa_exata:
        return mapa_exata, "tabela attendance (disciplina)", {}
    if mapa_legado:
        return mapa_legado, "tabela attendance (legado, sem disciplina)", {}
    if permitir_outra and por_disciplina:
        sid2, mapa2 = max(por_disciplina.items(), key=lambda kv: len(kv[1]))
        nome2 = None
        try:
            conn2 = get_db()
            r2 = conn2.execute("SELECT name FROM subjects WHERE id = ?", (sid2,)).fetchone()
            conn2.close()
            nome2 = r2["name"] if r2 else None
        except Exception:
            nome2 = None
        rotulo = nome2 or sid2
        return mapa2, f"tabela attendance (outra disciplina: {rotulo})", {
            "outra_disciplina": True,
            "disciplina": sid2,
            "disciplina_nome": nome2,
        }
    return None, None, {}


def attendance_turma_keys(turma_id):
    """Chaves candidatas da turma: o valor informado + equivalente id<->code."""
    keys = [str(turma_id)]
    try:
        conn = get_db()
        for r in conn.execute("SELECT id, code FROM classes").fetchall():
            rid, rcode = str(r["id"]), str(r["code"])
            if str(turma_id) == rcode and rid not in keys:
                keys.append(rid)
            elif str(turma_id) == rid and rcode not in keys:
                keys.append(rcode)
        conn.close()
    except Exception:
        pass
    return keys


def _attendance_exceptions():
    """Carrega (com cache) `attendance_exceptions.json` da pasta de plugins."""
    cache_key = "attendance_exceptions.json"
    if cache_key in _attendance_cache:
        return _attendance_cache[cache_key]
    data = {}
    for folder in ATTENDANCE_JSON_LOCATIONS:
        path = os.path.join(folder, cache_key)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    data = {}
            except Exception:
                data = {}
            break
    _attendance_cache[cache_key] = data
    return data


def _attendance_exception(turma_id, data_iso, disc_id):
    """Exceção manual para a aula.

    Chaves aceitas em `attendance_exceptions.json`:
      - ``"{turma}|{data}|{disc}"`` (específica) ou ``"{turma}|{data}"`` (dia).
    Valores: ``{"acao": "ignorar", "nota": "..."}`` ou
    ``{"acao": "usar_disciplina", "disciplina": "2", "nota": "..."}``.
    """
    exc = _attendance_exceptions()
    if not exc:
        return None, None
    for tk in attendance_turma_keys(turma_id):
        chave_disc = f"{tk}|{data_iso}|{disc_id}" if disc_id is not None else None
        chave_dia = f"{tk}|{data_iso}"
        if chave_disc and chave_disc in exc:
            return exc[chave_disc], chave_disc
        if chave_dia in exc:
            return exc[chave_dia], chave_dia
    return None, None


def load_attendance_map_for(turma_id, disc_id, data_iso):
    """Mapa de presença {RA/nome: status} de uma aula específica.

    Retorna ``(mapa, fonte, diagnostico)``:

    - ``diagnostico``: ``encontrou``, ``quantidade``, ``fontes`` (consultadas),
      ``outra_disciplina`` (fallback de outra disciplina), ``disciplina`` e
      ``excecao`` (se houver exceção manual).

    Prioridade das fontes:
      0. `attendance_exceptions.json` (ignorar / usar_disciplina);
      1. Tabela `attendance` do banco local (DATA -> TURMA -> DISCIPLINA, com
         fallback para outra disciplina da mesma turma/data);
      2. JSONs do plugin (data/repo/plugins → api/plugins), na ordem
         corrigido → normalizado → raw → planejado.

    Formatos JSON aceitos:
      - plano legado {turma: {data: {ra: status}}};
      - canônico    {turma: {disciplina: {data: {ra: status}}}};
      - data-first  {data: {turma: {disciplina: {ra: status}}}}.
    """
    diag = {
        "encontrou": False,
        "quantidade": 0,
        "fontes": [],
        "outra_disciplina": False,
        "disciplina": str(disc_id) if disc_id is not None else None,
        "excecao": None,
        "chave_excecao": None,
    }

    def _achou(entry, fonte, outra=False):
        diag["encontrou"] = True
        diag["quantidade"] = len(entry)
        diag["outra_disciplina"] = bool(outra)
        return entry, fonte, diag

    # 0) Exceções manuais
    exc, chave_exc = _attendance_exception(turma_id, data_iso, disc_id)
    if exc:
        diag["excecao"] = str(exc.get("nota") or exc.get("acao") or "")
        diag["chave_excecao"] = chave_exc
        acao = str(exc.get("acao") or "").lower()
        if acao == "ignorar":
            diag["fontes"].append(f"attendance_exceptions.json (ignorar: {chave_exc})")
            return {}, "exceção manual (ignorar)", diag
        if acao == "usar_disciplina" and exc.get("disciplina") is not None:
            disc_id = str(exc["disciplina"])
            diag["disciplina"] = disc_id
            diag["fontes"].append(f"attendance_exceptions.json (→ disciplina {disc_id})")

    # 1) Tabela attendance (banco local) — data -> turma -> disciplina
    diag["fontes"].append("tabela attendance")
    db_map, db_src, db_extra = load_attendance_from_db(turma_id, data_iso, disc_id)
    if db_map:
        return _achou(db_map, db_src, outra=bool(db_extra.get("outra_disciplina")))

    # 2) JSONs do plugin
    for att_name in ATTENDANCE_FILES_PRIORITY:
        att_data = load_attendance_json(att_name)
        if not att_data:
            continue
        diag["fontes"].append(att_name)
        primeira_chave_top = str(next(iter(att_data.keys()), ""))

        # Formato data-first {data: {turma: {disciplina: {ra: status}}}}
        if re.match(r"\d{4}-\d{2}-\d{2}$", primeira_chave_top):
            bloco_data = att_data.get(data_iso)
            if not isinstance(bloco_data, dict):
                continue
            for tk in attendance_turma_keys(turma_id):
                bloco_turma = bloco_data.get(tk)
                if not isinstance(bloco_turma, dict):
                    continue
                entry = bloco_turma.get(str(disc_id))
                if isinstance(entry, dict) and entry:
                    return _achou(entry, f"{att_name} (data -> turma -> disciplina)")
                for dk, dias in bloco_turma.items():
                    if isinstance(dias, dict) and dias:
                        outra = disc_id is not None and str(dk) != str(disc_id)
                        return _achou(dias, f"{att_name} (data -> turma, disc {dk})",
                                      outra=outra)
            continue

        # Formato turma-first: plano ou canônico
        for tk in attendance_turma_keys(turma_id):
            bloco_turma = att_data.get(tk)
            if not isinstance(bloco_turma, dict):
                continue
            # Formato plano {data: {ra: status}}: primeiro nível são datas.
            primeira_chave = str(next(iter(bloco_turma.keys()), ""))
            if re.match(r"\d{4}-\d{2}-\d{2}$", primeira_chave):
                entry = bloco_turma.get(data_iso)
                if isinstance(entry, dict) and entry:
                    return _achou(entry, att_name)
                continue
            # Formato aninhado: 1) disciplina exata
            bloco_disc = bloco_turma.get(str(disc_id))
            if isinstance(bloco_disc, dict):
                entry = bloco_disc.get(data_iso)
                if isinstance(entry, dict) and entry:
                    return _achou(entry, att_name)
            # 2) fallback: qualquer disciplina dessa turma com essa data
            for dk, dias in bloco_turma.items():
                if not isinstance(dias, dict):
                    continue
                entry = dias.get(data_iso)
                if isinstance(entry, dict) and entry:
                    outra = disc_id is not None and str(dk) != str(disc_id)
                    return _achou(entry, f"{att_name} (disc {dk})", outra=outra)
    return {}, None, diag
