"""Grade horária: leitura e edição dos 3 espelhos (IS-047).

Espelhos:
  1. SQLite local `weekly_schedule` — lido pelo gerador de planos (8510).
  2. `data/repo/plugins/grade_horaria.json` — lido pelos plugins do portal
     (Registro de Aula e Grade Semanal).
  3. Supabase `weekly_schedule` — nuvem; o plugin Grade Semanal funde o JSON
     com a nuvem ("Sincronizar com Nuvem").

Toda edição feita por aqui é gravada nos 3 espelhos de uma vez, para que
gerador, Registro do portal e visualização na nuvem não divirjam (mesma
lição do triplo espelho da IS-044).
"""

import json
import os
import sqlite3
import sys
from datetime import datetime

DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
HORARIOS_PADRAO = ["07:10", "08:10", "09:10", "10:10", "10:30", "11:30",
                   "12:30", "13:30", "14:30", "14:50", "15:50", "16:50"]

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_CORE_DIR)                        # apps/planejamento_registro
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))   # SysAva
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

GRADE_JSON = os.path.join(_PROJECT_ROOT, "data", "repo", "plugins", "grade_horaria.json")
PROF_EDICAO = "Config 8510"


def dia_da_data(valor, fmt):
    """'03/06/2026' ou '2026-06-03' -> 'Quarta' (None se ilegível)."""
    from datetime import datetime as _dt
    for f in (fmt, "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return DIAS[_dt.strptime(str(valor)[:10], f).weekday()]
        except ValueError:
            continue
    return None


# ===========================================================================
# Leitura (3 espelhos)
# ===========================================================================
def carregar_sqlite(conn=None):
    """{turma: {dia: {horário: componente}}} do SQLite local (dedup por chave)."""
    from . import banco
    own = conn is None
    if own:
        conn = banco.get_db()
    try:
        rows = conn.execute(
            "SELECT class_name, day_of_week, time_slot, subject_name "
            "FROM weekly_schedule ORDER BY rowid").fetchall()
        grade = {}
        for r in rows:
            turma, dia, slot = r["class_name"], r["day_of_week"], r["time_slot"]
            if not turma or dia not in DIAS:
                continue
            grade.setdefault(turma, {}).setdefault(dia, {})[slot] = r["subject_name"]
        return grade
    finally:
        if own:
            conn.close()


def carregar_json():
    """grade_horaria.json completo ({turma: {dia: {h: s}, 'config_horarios': [...]}})."""
    try:
        with open(GRADE_JSON, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def carregar_supabase():
    """{turma: {dia: {h: s}}} da nuvem, ou None se indisponível/sem conexão."""
    try:
        from services import database as svc
        client = svc.get_supabase()
        if client is None:
            return None
        res = client.table("weekly_schedule").select("*").execute()
        grade = {}
        for row in res.data or []:
            turma, dia, slot = row.get("class_name"), row.get("day_of_week"), row.get("time_slot")
            if not turma or dia not in DIAS:
                continue
            grade.setdefault(turma, {}).setdefault(dia, {})[slot] = row.get("subject_name")
        return grade
    except Exception:
        return None


def turma_code(turma_nome):
    """classes.name -> classes.code ('309197'); None se não achar."""
    from . import banco
    conn = banco.get_db()
    try:
        row = conn.execute("SELECT code FROM classes WHERE name = ?",
                           (turma_nome,)).fetchone()
        return row["code"] if row else None
    finally:
        conn.close()


def class_id(turma_nome):
    from . import banco
    conn = banco.get_db()
    try:
        row = conn.execute("SELECT id FROM classes WHERE name = ?",
                           (turma_nome,)).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


# ===========================================================================
# Monitoração
# ===========================================================================
def divergencias(turma, grade_sqlite, grade_json, grade_nuvem):
    """Linhas Dia|Horário|SQLite|JSON|Nuvem para a turma, com status."""
    grade_json = grade_json or {}
    grade_nuvem = grade_nuvem  # pode ser None (indisponível)

    def slots(grade):
        out = {}
        if not grade:
            return out
        for dia, mapa in (grade.get(turma) or {}).items():
            if not isinstance(mapa, dict) or dia not in DIAS:
                continue
            for h, s in mapa.items():
                out[(dia, h)] = s
        return out

    s_sql, s_json, s_nuv = slots(grade_sqlite), slots(grade_json), slots(grade_nuvem)
    linhas = []
    for (dia, h) in sorted(set(s_sql) | set(s_json) | set(s_nuv),
                           key=lambda k: (DIAS.index(k[0]), k[1])):
        v_sql = s_sql.get((dia, h), "—")
        v_json = s_json.get((dia, h), "—")
        v_nuv = s_nuv.get((dia, h), "—") if grade_nuvem is not None else "n/d"
        valores = {v_sql, v_json} | ({v_nuv} if grade_nuvem is not None else set())
        status = "✅ igual" if len(valores) == 1 else "⚠️ divergente"
        linhas.append({"Dia": dia, "Horário": h, "SQLite": v_sql,
                       "JSON": v_json, "Nuvem": v_nuv, "Status": status})
    return linhas


def impacto(turma_nome):
    """Por (dia, horário): componente na grade + nº de aulas registradas e
    planos da turma — revela slots com plano fora da grade (ex.: aulas que
    mudaram de dia)."""
    from . import banco
    code = turma_code(turma_nome)
    grade = carregar_sqlite().get(turma_nome, {})
    linhas = {}
    for dia, mapa in grade.items():
        for h, s in (mapa or {}).items():
            linhas[(dia, h)] = {"Dia": dia, "Horário": h, "Componente": s,
                                "Registradas": 0, "Planos": 0}
    if code:
        conn = banco.get_db()
        try:
            for r in conn.execute(
                    "SELECT data_aula, horario FROM historico_aulas WHERE turma_id = ?",
                    (code,)).fetchall():
                dia = dia_da_data(r["data_aula"], "%d/%m/%Y")
                h = str(r["horario"] or "").split(" às ")[0].strip()
                if dia and h:
                    d = linhas.setdefault((dia, h), {"Dia": dia, "Horário": h,
                                                     "Componente": "—",
                                                     "Registradas": 0, "Planos": 0})
                    d["Registradas"] += 1
            for r in conn.execute(
                    "SELECT data_planejada, horario FROM planejamento WHERE turma_id = ?",
                    (code,)).fetchall():
                dia = dia_da_data(r["data_planejada"], "%Y-%m-%d")
                h = str(r["horario"] or "").strip()
                if dia and h:
                    d = linhas.setdefault((dia, h), {"Dia": dia, "Horário": h,
                                                     "Componente": "—",
                                                     "Registradas": 0, "Planos": 0})
                    d["Planos"] += 1
        finally:
            conn.close()
    saida = []
    for (dia, h) in sorted(linhas, key=lambda k: (DIAS.index(k[0]), k[1])):
        d = dict(linhas[(dia, h)])
        d["Aviso"] = ("⚠️ planos fora da grade"
                      if d["Componente"] == "—" and d["Planos"] > 0 else "")
        saida.append(d)
    return saida


# ===========================================================================
# Edição (grava nos 3 espelhos)
# ===========================================================================
def _sqlite_apply(turma, dia, slot, subj):
    """Apaga (turma, dia, slot) — com todas as linhas/duplicatas — e reinsere
    `subj` (None = só remove). Retorna nº de linhas removidas."""
    from . import banco
    conn = banco.get_db()
    try:
        n = conn.execute(
            "DELETE FROM weekly_schedule WHERE class_name = ? AND day_of_week = ? "
            "AND time_slot = ?", (turma, dia, slot)).rowcount
        if subj:
            conn.execute(
                "INSERT INTO weekly_schedule (id, class_name, day_of_week, time_slot, "
                "subject_name, professor_name, created_at, class_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (None, turma, dia, slot, subj, PROF_EDICAO,
                 datetime.now().isoformat(timespec="seconds"), class_id(turma)))
        conn.commit()
        return n
    finally:
        conn.close()


def _json_apply(turma, dia, slot, subj):
    grade = carregar_json()
    turma_d = grade.setdefault(turma, {})
    dia_d = turma_d.setdefault(dia, {})
    if subj:
        dia_d[slot] = subj
    else:
        dia_d.pop(slot, None)
    with open(GRADE_JSON, "w", encoding="utf-8") as f:
        json.dump(grade, f, indent=4, ensure_ascii=False)
    return True


def _supabase_apply(turma, dia, slot, subj):
    """Delete + upsert do (turma, dia, slot) na nuvem. 'ok' | 'desconectado' | 'erro: ...'."""
    try:
        from services import database as svc
        client = svc.get_supabase()
        if client is None:
            return "desconectado"
        client.table("weekly_schedule").delete().match({
            "class_name": turma, "day_of_week": dia, "time_slot": slot
        }).execute()
        if subj:
            client.table("weekly_schedule").upsert({
                "class_name": turma, "day_of_week": dia, "time_slot": slot,
                "subject_name": subj, "professor_name": PROF_EDICAO,
            }, on_conflict="class_name, day_of_week, time_slot").execute()
        return "ok"
    except Exception as e:
        return f"erro: {e}"


def _aplicar(turma, dia, slot, subj, sync_supabase=True):
    """Grava (dia, slot) -> subj (None remove) nos 3 espelhos; relatório."""
    removidas = _sqlite_apply(turma, dia, slot, subj)
    _json_apply(turma, dia, slot, subj)
    nuvem = _supabase_apply(turma, dia, slot, subj) if sync_supabase else "pulado"
    acao = "definido" if subj else "removido"
    return {"Ação": f"{acao} {dia} {slot} -> {subj or '—'}",
            "SQLite": f"{removidas} linha(s) apagada(s)",
            "JSON": "ok", "Nuvem": nuvem}


def mover(turma, dia_origem, slot_origem, dia_destino, slot_destino,
          sync_supabase=True):
    """Move um slot mantendo o componente. Relatório com 2 ações."""
    grade = carregar_sqlite().get(turma, {})
    subj = grade.get(dia_origem, {}).get(slot_origem)
    if not subj:
        return {"erro": f"slot de origem não existe na grade: "
                        f"{dia_origem} {slot_origem}"}
    if (dia_origem, slot_origem) == (dia_destino, slot_destino):
        return {"erro": "origem e destino são iguais"}
    rel = [_aplicar(turma, dia_origem, slot_origem, None, sync_supabase),
           _aplicar(turma, dia_destino, slot_destino, subj, sync_supabase)]
    return {"ok": rel}


def adicionar(turma, dia, slot, subj, sync_supabase=True):
    if not subj:
        return {"erro": "componente vazio"}
    return {"ok": [_aplicar(turma, dia, slot, subj, sync_supabase)]}


def remover(turma, dia, slot, sync_supabase=True):
    grade = carregar_sqlite().get(turma, {})
    if slot not in grade.get(dia, {}):
        return {"erro": f"slot não existe na grade: {dia} {slot}"}
    return {"ok": [_aplicar(turma, dia, slot, None, sync_supabase)]}
