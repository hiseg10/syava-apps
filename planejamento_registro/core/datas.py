"""Regras de data do planejamento.

Regra de início da geração:

- Dias úteis: ``max(data_corte, última_aula_registrada + 1 dia)`` por
  turma/disciplina (considerando aliases base/filha).
- Sábados letivos: seguem apenas a ``data_corte``.
- Disciplinas sem histórico começam na ``data_corte``.
- Fila Disc.Tec. (modulares/mensais): o piso acima é elevado a
  ``última_aula_modular + 1 dia`` por turma (IS-043) — o portal manda sobre
  a janela do plano anual e sua tolerância; aplicado no gerador via
  :func:`ultima_aula_modular`.
"""

from datetime import datetime, timedelta

from .banco import get_config, get_db

DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y")


def parse_data(s):
    """Interpreta ``dd/mm/yyyy``, ``yyyy-mm-dd`` ou ``dd-mm-yyyy``."""
    s = str(s or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s[:10], fmt).date()
        except Exception:
            continue
    return None


def data_corte(default=None):
    """Data de corte configurada em ``master_config`` (``data_corte_planejamento``)."""
    try:
        valor = get_config("data_corte_planejamento")
        if valor:
            return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()
    except Exception:
        pass
    return default


def _alias_maps():
    """(alias_id -> base_id, base_id -> {ids equivalentes})."""
    alias_to_base = {}
    base_to_aliases = {}
    conn = get_db()
    try:
        for r in conn.execute("SELECT alias_id, base_id FROM discipline_aliases"):
            try:
                a, b = int(r[0]), int(r[1])
            except Exception:
                continue
            alias_to_base[a] = b
            base_to_aliases.setdefault(b, set()).add(b)
            base_to_aliases[b].add(a)
    except Exception:
        pass
    finally:
        conn.close()
    return alias_to_base, base_to_aliases


def _turma_disc_configs():
    """{(turma_str, disciplina_str): aliases_id}."""
    out = {}
    conn = get_db()
    try:
        for r in conn.execute(
            "SELECT turma_id, disciplina_id, aliases_id FROM turma_disciplina_config"
        ):
            out[(str(r[0]), str(r[1]))] = r[2]
    except Exception:
        pass
    finally:
        conn.close()
    return out


def ultima_aula_por_disciplina():
    """{(turma_str, disciplina_str): date} — última aula registrada no portal."""
    out = {}
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT turma_id, disciplina_id, data_aula FROM historico_aulas "
            "WHERE turma_id IS NOT NULL AND disciplina_id IS NOT NULL "
            "AND data_aula IS NOT NULL"
        ).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    for r in rows:
        d = parse_data(r["data_aula"])
        if not d:
            continue
        k = (str(r["turma_id"]), str(r["disciplina_id"]))
        if k not in out or d > out[k]:
            out[k] = d
    return out


def ultima_aula_modular(ids_modulares):
    """Ids modulares expandidos e última aula modular registrada por turma.

    Retorna ``(ids_expandidos, {turma_str: date})``. É o piso da fila
    Disc.Tec. aplicado ANTES do calendário anual (IS-043): a disciplina
    modular seguinte só começa depois da última aula registrada entre as
    janelas modulares da turma — mesmo que a tolerância (±N dias) da janela
    ainda permita a data. Os ids são expandidos via ``discipline_aliases``
    (base <-> aliases) para casar com o ``disciplina_id`` do histórico.
    """
    alias_to_base, base_to_aliases = _alias_maps()
    ids = set()
    for i in (ids_modulares or []):
        s = str(i).strip()
        if not s.isdigit():
            continue
        n = int(s)
        b = alias_to_base.get(n, n)
        ids.add(str(n))
        ids.add(str(b))
        ids.update(str(a) for a in base_to_aliases.get(b, set()))
    out = {}
    if not ids:
        return ids, out
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT turma_id, disciplina_id, data_aula FROM historico_aulas "
            "WHERE turma_id IS NOT NULL AND disciplina_id IS NOT NULL "
            "AND data_aula IS NOT NULL"
        ).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    for r in rows:
        if str(r["disciplina_id"]) not in ids:
            continue
        d = parse_data(r["data_aula"])
        if not d:
            continue
        t = str(r["turma_id"])
        if t not in out or d > out[t]:
            out[t] = d
    return ids, out


def inicio_geracao(corte, data_inicio):
    """Mapa de início da geração para dias úteis.

    Retorna ``(inicio_map, base)``:

    - ``inicio_map[(turma_str, disc_str)] -> date``: data mínima para gerar
      planos daquela disciplina (dia seguinte à última aula, com piso no corte).
    - ``base``: data usada quando a disciplina não tem histórico (o corte).
    """
    base = corte or data_inicio
    ultima = ultima_aula_por_disciplina()
    configs = _turma_disc_configs()
    alias_to_base, base_to_aliases = _alias_maps()

    def _keys(tid, did):
        keys = {(tid, did)}
        di = int(did) if str(did).isdigit() else None
        if di is not None:
            if di in alias_to_base:
                b = alias_to_base[di]
                keys.add((tid, str(b)))
                for a in base_to_aliases.get(b, set()):
                    keys.add((tid, str(a)))
            for a in base_to_aliases.get(di, set()):
                keys.add((tid, str(a)))
        for (ct, cd), al in configs.items():
            if ct == tid and (cd == did or (al is not None and str(al) == did)):
                keys.add((tid, cd))
                if al is not None:
                    keys.add((tid, str(al)))
        return keys

    inicio_map = {}
    for (tid, did), d in ultima.items():
        nxt = d + timedelta(days=1)
        if corte and nxt < corte:
            nxt = corte
        for k in _keys(tid, did):
            if k not in inicio_map or nxt > inicio_map[k]:
                inicio_map[k] = nxt

    return inicio_map, base


def inicio_disciplina(inicio_map, base, turma_code, disc_id, alias_id=None):
    """Data mínima (dias úteis) para uma turma/disciplina."""
    chaves = [(str(turma_code), str(disc_id))]
    if alias_id is not None:
        chaves.append((str(turma_code), str(alias_id)))
    valores = [inicio_map[k] for k in chaves if k in inicio_map]
    return max(valores) if valores else base
