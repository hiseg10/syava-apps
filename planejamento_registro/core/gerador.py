"""Gerador de planos de aula (.txt) a partir do banco SQLite local.

Modulo independente da API (sem FastAPI). Reutilizado pelo app de
Planejamento e Registro e pelo endpoint ``/gerar-txt-planos``.
"""

import os
import re
import json
from datetime import date, datetime, timedelta

from . import banco, datas as regras_datas
from .banco import PROJECT_ROOT
from tools import database_model
from tools.plan_utils import (
    clean_text_local,
    parse_lesson_markdown,
    normalize_key_local,
    normalize_horario_range,
    generate_lesson_log,
)


def _montar_conteudo_enriquecido(title: str, objetivos_list: list, conteudo_section: str, fallback_desc: str) -> str:
    """
    Monta o campo [CONTEUDO] enriquecido: título + objetivos.
    
    Prioridade:
    1. Título + Objetivos (se existirem)
    2. Seção conteúdo do markdown
    3. Descrição como fallback
    """
    parts = []
    
    # Adiciona o título da aula
    if title:
        parts.append(clean_text_local(title, 200))
    
    # Adiciona os objetivos (até 3)
    if objetivos_list:
        objetivos_text = "; ".join(objetivos_list[:3])
        parts.append(f"Objetivos: {clean_text_local(objetivos_text, 300)}")
    
    # Se tem partes, junta com separador
    if parts:
        return " | ".join(parts)
    
    # Fallback: usa seção conteúdo ou descrição
    if conteudo_section:
        return clean_text_local(conteudo_section, 500)
    
    return clean_text_local(fallback_desc, 500) if fallback_desc else ''


def _eh_lesson_planejavel(titulo):
    """Verdadeiro apenas para títulos de lesson no padrão 'Aula XX ...'.

    Lessons fragmentadas/placeholders ('--- Configurações Iniciais ---',
    'Setup PowerShell', '[Markdown] Estrutura...', etc.) não fazem parte da
    fila elegível de planejamento.
    """
    if not titulo:
        return False
    return bool(re.match(r'^\s*Aula\s+\d+', str(titulo), re.IGNORECASE))


def _numero_aula(titulo):
    """Extrai o número sequencial 'N' de um título 'Aula N ...' (str ou int)."""
    m = re.match(r'^\s*Aula\s+(\d+)', str(titulo or ''), re.IGNORECASE)
    return int(m.group(1)) if m else None


def _ordenar_lessons_fila(lessons_list):
    """Orderna a fila por número crescente da Aula (''Aula 1 …'' < ''Aula 2 …'').

    Títulos fora do padrão ('Aula N') ficam por último; empates de mesmo número
    mantêm a ordem original (duplicatas legadas da auditoria de lessons).
    """
    def _chave(l):
        n = _numero_aula(l.get('title'))
        if n is None:
            return (1, 0)
        return (0, n)
    return sorted(lessons_list, key=_chave)


def gerar_txt_planos(
    auto_confirm: bool = True,
    output_dir: str = "pendentes",
    force_overwrite: bool = False,
    turma_id: str = "",
    disciplina_id: str = "",
    estrategia: str = None,
    aula_min: int = None,
    aula_max: int = None
):
    """
    Gera arquivos .txt de plano de aula a partir do banco de dados.
    Replica a logica de preparar_planos.py + preenchedor_planos.py via API.

    output_dir: 'pendentes' ou 'prontas'
    force_overwrite: sobrescreve arquivos existentes (padrao: False, mantem edicao manual)
    turma_id: filtra por turma (aceita code 309197, id 1 ou nome)
    disciplina_id: filtra por disciplina (aceita id ou nome)
    estrategia: tipo de estratégia a aplicar nos planos gerados (ex.: "Aula
        expositiva", "Aula baseada em projetos", "Aula de atividades em
        laboratório"). Padrão: None -> "Aula expositiva e prática."
    aula_min / aula_max: intervalo de número de aula (seq) a gerar. Pular
        (None) ou 0 não aplica filtro.
    """

    def extract_start_time_key_local(horario_str):
        if not horario_str:
            return ""
        clean = re.sub(r'[^0-9]', '', horario_str.split('às')[0]).zfill(4)
        return clean[:4] if len(clean) >= 4 else clean

    def parse_date_universal_local(date_str):
        if not date_str:
            return None
        date_str = date_str.strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        return None

    # --- Constantes do project_constants (que não existe no disco) ---
    SUBJECT_ALIASES = {
        "PCII": "PENSAMENTOCOMPUTACIONALII",
        "IA": "INTELIGENCIAARTIFICIAL",
        "MENTTECII": "MENTORIASTECII",
        "POO": "PROGRAMACAOORIENTADAAOBJETOSPOO",
        "PWFE": "PROGRAMACAOWEBFRONTEND",
        "PROGWEBFRONTEND": "PROGRAMACAOWEBFRONTEND",
    }

    DISCIPLINAS_PARA_DUPLICAR = {
        6,   # PROGRAMAÇÃO WEB FRONT-END
        31,  # PROGRAMAÇÃO WEB FRONT-END (Turma I-B)
        33,  # PROGRAMAÇÃO WEB FRONT-END 2026A
        34,  # PROGRAMAÇÃO WEB FRONT-END 2026B
    }

    GENERIC_LABELS = ['Disc.Tec.', 'Disc. Tec.', 'DISC.TEC', 'DISC TEC', 'DISC.TEC.', 'DISCTEC']

    def resolve_subject_info_local(query_name, mapa_disciplinas):
        """Resolução robusta de disciplina: Direto, Alias, Substring."""
        norm_query = normalize_key_local(query_name)
        # 1. Busca Direta
        if norm_query in mapa_disciplinas:
            return mapa_disciplinas[norm_query]
        # 2. Busca por prefixo (filha)
        for norm_db_name, info in mapa_disciplinas.items():
            if norm_query.startswith(norm_db_name):
                return info
        # 3. Busca via aliases
        alias_norm = SUBJECT_ALIASES.get(norm_query)
        if alias_norm and alias_norm in mapa_disciplinas:
            return mapa_disciplinas[alias_norm]
        # 4. Busca por substring
        for norm_db_name, info in mapa_disciplinas.items():
            if norm_query in norm_db_name:
                return info
        return None

    def get_next_modular_subject(restricoes, next_aula_num, mapa_disciplinas, curr_date, turma_id, turma_to_monthly):
        """Encontra a próxima disciplina modular ativa que precisa de aulas."""
        curr_date_obj = curr_date if isinstance(curr_date, datetime) else datetime.strptime(curr_date, "%Y-%m-%d").date()
        
        # Filtra a disciplina esperada para esta turma
        disciplina_esperada = turma_to_monthly.get(turma_id)
        # print(f"DEBUG: Turma {turma_id} -> Disciplina esperada: {disciplina_esperada}")
        
        # Filtra apenas modulares (< 300 dias)
        modulares = []
        for k, v in restricoes.items():
            try:
                # Verifica se a disciplina (ou seu alias) coincide com a esperada para a turma
                if disciplina_esperada:
                    # Normaliza para comparar
                    nome_restricao = normalize_key_local(k)
                    nome_esperado = normalize_key_local(disciplina_esperada)
                    # Verifica flexibilidade: se um é parte do outro ou se correspondem
                    # (ex: PROGRAMACAOWEBFRONTEND2026A contem PROGRAMACAOWEBFRONTEND)
                    if nome_restricao not in nome_esperado and nome_esperado not in nome_restricao:
                        continue
                
                m_ini = datetime.strptime(v['data_inicio'], "%d/%m/%Y").date()
                m_fim = datetime.strptime(v['data_fim'], "%d/%m/%Y").date()
                if (m_fim - m_ini).days > 300:
                    continue  # Anual, pular
                if m_ini <= curr_date_obj <= m_fim:
                    modulares.append((k, m_ini, m_fim))
            except:
                continue
        # Ordena por data de início
        modulares.sort(key=lambda x: x[1])
        for mod_name, _, _ in modulares:
            d_info = resolve_subject_info_local(mod_name, mapa_disciplinas)
            if d_info:
                did = d_info['id']
                current_count = next_aula_num.get(did, 0)
                if current_count < 50:  # Limite generoso
                    return mod_name, d_info
        return None, None

    # --- Constantes internas ---
    LIMITE_AULAS_REGULAR = 40
    GENERIC_KEYWORDS = ["DISCTEC", "DISCITEC", "TECNICO", "DISC_TEC", "DISC_TECNICA"]
    # IDs de disciplinas genéricas que NÃO devem ser usadas diretamente
    EXCLUDED_SUBJECT_IDS = {99}  # Disc.Tec.

    # Mapeamento de abreviações da grade → nomes reais no banco
    GRADE_ALIAS_MAP = {
        "PCII": "PENSAMENTO COMPUTACIONAL II",
        "IA": "INTELIGÊNCIA ARTIFICIAL",
        "MENTTECII": "MENTORIAS TEC II",
        "MENTORIATECNICAII": "MENTORIAS TEC II",
        "PENSAMENTOCOMPUTACIONALII": "PENSAMENTO COMPUTACIONAL II",
        "PROGRAMACAOESTRUTURADA": "PROGRAMACAO ESTRUTURADA",
        "POO": "PROGRAMAÇÃO ORIENTADA A OBJETOS - POO",
        "PWFE": "PROGRAMAÇÃO WEB FRONT-END",
        "PROGWEBFRONTEND": "PROGRAMAÇÃO WEB FRONT-END",
    }

    # Dia da semana em português
    dia_map = {0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta"}
    dia_map_rev = {"Segunda": 0, "Terça": 1, "Quarta": 2, "Quinta": 3, "Sexta": 4}

    def _norm_dia(s):
        """Normaliza nome de dia (sem acento/pontuação) para comparar 'Terca' == 'Terça'."""
        import unicodedata as _ud
        if not s:
            return ""
        s = str(s).replace('ª', 'a').replace('º', 'o')
        s = _ud.normalize('NFD', s)
        s = "".join(c for c in s if _ud.category(c) != 'Mn')
        return re.sub(r'[^A-Z0-9]', '', s.upper())

    # --- Validação do diretório de saída ---
    valid_dirs = ["pendentes", "prontas", "padrao"]
    if output_dir not in valid_dirs:
        raise ValueError(f"output_dir deve ser um de: {valid_dirs}")
    
    output_path = os.path.join(PROJECT_ROOT, "aulas", output_dir)
    os.makedirs(output_path, exist_ok=True)

    # --- Conexão com o banco ---
    conn = banco.get_db_connection()
    cursor = conn.cursor()

    # 1. Carregar disciplinas
    cursor.execute("SELECT id, name FROM subjects")
    subjects_raw = [dict(r) for r in cursor.fetchall()]
    mapa_discs = {}
    mapa_discs_norm = {}
    mapa_ids = {}  # str(id) -> full info dict
    mapa_disciplinas = {}  # normalized_name -> full info dict
    for s in subjects_raw:
        mapa_discs[s['name']] = s['id']
        norm = normalize_key_local(s['name'])
        mapa_discs_norm[norm] = s['id']
        mapa_ids[str(s['id'])] = s
        mapa_disciplinas[norm] = {**s, 'norm_name': norm}

    # 2. Carregar turmas
    cursor.execute("SELECT id, code, name, portal_name FROM classes")
    classes_raw = [dict(r) for r in cursor.fetchall()]
    mapa_turmas = {}
    mapa_turmas_norm = {}
    mapa_id_para_code = {}
    for c in classes_raw:
        code = str(c['code'])
        mapa_turmas[c['name']] = code
        mapa_turmas_norm[normalize_key_local(c['name'])] = code
        mapa_id_para_code[str(c['id'])] = code
        if c.get('portal_name'):
            mapa_turmas[c['portal_name']] = code
            mapa_turmas_norm[normalize_key_local(c['portal_name'])] = code

    # 2.1 Carregar disciplina mensal configurada por turma (da tabela settings)
    monthly_by_class = {}
    try:
        cursor.execute("SELECT chave, valor FROM settings WHERE chave LIKE 'disciplina_mensal_%'")
        for r in cursor.fetchall():
            chave = r['chave']
            valor = r['valor']
            if chave.startswith('disciplina_mensal_') and chave != 'disciplina_mensal_atual':
                mid = chave.replace('disciplina_mensal_', '')
                monthly_by_class[mid] = valor
    except:
        pass

    # Mapear turma_id -> nome da disciplina mensal (nao sombrear o parametro turma_id!)
    turma_to_monthly = {}
    for mid, disc_name in monthly_by_class.items():
        turma_code_m = mapa_id_para_code.get(mid, mid)
        turma_to_monthly[turma_code_m] = disc_name

    # 3. Carregar grade horária
    cursor.execute("SELECT class_name, day_of_week, time_slot, subject_name FROM weekly_schedule")
    grade_raw = [dict(r) for r in cursor.fetchall()]

    # Deduplicar slots (turma, dia, horário): a grade contém linhas repetidas
    # (ex.: "I.A.", "P.C.II"/"P.C. II", "Disc.Tec." duplicadas no mesmo dia/horário).
    # Cada slot = 1 aula; processar as duplicatas fazia o seq avançar +2 por semana
    # e a numeração dos planos pular os pares (IS-019).
    _grade_vistos = set()
    _grade_dedup = []
    for _g in grade_raw:
        _key = (str(_g['class_name']), str(_g['day_of_week']), str(_g['time_slot']))
        if _key in _grade_vistos:
            continue
        _grade_vistos.add(_key)
        _grade_dedup.append(_g)
    grade_raw = _grade_dedup

    # 4. Carregar histórico (para evitar duplicatas)
    # A raspagem grava os registros com o NOME ATUAL da turma. Linhas legadas de
    # bots antigos (nome antigo, horário/nº duplicados) são ignoradas: não existem
    # mais no portal e inflam os contadores, travando a geração (IS-015/IS-016).
    cursor.execute("SELECT code, name FROM classes")
    _classes_nome = {str(r['code']): r['name'] for r in cursor.fetchall()}
    cursor.execute("SELECT data_aula, horario, turma_id, disciplina_id, turma, lesson_index FROM historico_aulas")
    historico_rows = [dict(r) for r in cursor.fetchall()]
    _turmas_com_canonico = {
        str(r['turma_id']) for r in historico_rows
        if _classes_nome.get(str(r['turma_id'])) == r.get('turma')
    }
    turmas_sem_canonico = set(_classes_nome) - _turmas_com_canonico

    def _eh_registro_canonico(r):
        turma_str = str(r['turma_id'])
        return (turma_str in turmas_sem_canonico) or (_classes_nome.get(turma_str) == r.get('turma'))

    historico_set = set()
    historico_dates_by_turma = {}
    hist_count = {}  # (turma_str, disc_str) -> (total_aulas, maior_lesson_index)
    for r in historico_rows:
        if r['turma_id'] is None or r.get('disciplina_id') is None:
            continue
        turma_str = str(r['turma_id'])
        if not _eh_registro_canonico(r):
            continue
        key = (turma_str, str(r['disciplina_id']))
        cnt, mxi = hist_count.get(key, (0, 0))
        hist_count[key] = (cnt + 1, max(mxi, int(r.get('lesson_index') or 0)))
        d_obj = parse_date_universal_local(r['data_aula'])
        if d_obj and r['horario']:
            d_iso = d_obj.isoformat()
            h_key = extract_start_time_key_local(r['horario']).zfill(4)
            historico_set.add((d_iso, h_key, turma_str))
            if turma_str not in historico_dates_by_turma:
                historico_dates_by_turma[turma_str] = set()
            historico_dates_by_turma[turma_str].add(d_iso)

    # 5b. Carregar mapa de aliases de disciplina (ANTES de planejamento_set)
    # Alias permite que IDs com sufixo (33, 34) sejam tratados como ID base (6)
    discipline_aliases_map = {}
    alias_to_base = {}   # alias_id -> base_id
    base_to_aliases = {} # base_id -> set of alias_ids
    try:
        cursor.execute("SELECT alias_id, base_id, descricao FROM discipline_aliases")
        for row in cursor.fetchall():
            discipline_aliases_map[row[0]] = {'alias_id': row[0], 'base_id': row[1], 'descricao': row[2]}
            alias_to_base[row[0]] = row[1]
            if row[1] not in base_to_aliases:
                base_to_aliases[row[1]] = set()
            base_to_aliases[row[1]].add(row[0])
            # base also maps to itself
            base_to_aliases[row[1]].add(row[1])
    except:
        pass

    # 5. Carregar planejamento pendente (para evitar duplicatas)
    # IMPORTANTE: inclui disciplina_id na chave para deteccao por alias
    # Se ja existe plano com disc_id=6, tambem marca disc_id=33 como ocupado
    cursor.execute("SELECT data_planejada, horario, turma_id, disciplina_id, status FROM planejamento")
    planejamento_set = set()           # (date, h_key, turma_code) - compat antigo
    planejamento_by_turma_date = {}    # (turma_code, date) -> set of disciplina_ids
    for r in cursor.fetchall():
        if r['turma_id'] and r['horario']:
            h_key = extract_start_time_key_local(r['horario']).zfill(4)
            turma_c = str(r['turma_id'])
            planejamento_set.add((r['data_planejada'], h_key, turma_c))
            # Indexar por turma+data para deteccao por alias
            key_turma_date = (turma_c, r['data_planejada'])
            if key_turma_date not in planejamento_by_turma_date:
                planejamento_by_turma_date[key_turma_date] = set()
            did = r['disciplina_id']
            planejamento_by_turma_date[key_turma_date].add(did)
            # Se alias (ex: 33), tambem marca o base (ex: 6)
            if did in alias_to_base:
                planejamento_by_turma_date[key_turma_date].add(alias_to_base[did])
            # Se base (ex: 6), tambem marca todos os aliases (33, 34)
            if did in base_to_aliases:
                planejamento_by_turma_date[key_turma_date].update(base_to_aliases[did])

    # 6. Carregar aulas (lessons) - ordenadas por subject_id e id ASC
    cursor.execute("""
        SELECT id, title, description, video_url, subject_id
        FROM lessons
        ORDER BY subject_id, id ASC
    """)
    lessons_raw = [dict(r) for r in cursor.fetchall()]
    lessons_by_subject = {}
    for l in lessons_raw:
        sid = l['subject_id']
        keys_to_index = [sid, str(sid)]
        if str(sid).isdigit():
            keys_to_index.append(int(sid))
        for k in set(keys_to_index):
            if k not in lessons_by_subject:
                lessons_by_subject[k] = []
            lessons_by_subject[k].append(l)
    # Fila de planejamento em ordem crescente de Aula (não por id de inserção)
    for k in lessons_by_subject:
        lessons_by_subject[k] = _ordenar_lessons_fila(lessons_by_subject[k])

    # 7. Carregar calendário letivo
    calendario = database_model.get_config('calendario_letivo.json', PROJECT_ROOT) or {}
    data_inicio_str = calendario.get('data_inicio', '01/02/2026')
    data_fim_str = calendario.get('data_fim', '31/12/2026')
    data_inicio = datetime.strptime(data_inicio_str, "%d/%m/%Y").date()
    data_fim = datetime.strptime(data_fim_str, "%d/%m/%Y").date()

    # 7b. Configuração de sábados letivos / reposição
    sabados_config = {}
    for sat in calendario.get('sabados_letivos', []):
        d_iso = sat.get('data_iso')
        if not d_iso and sat.get('data'):
            try:
                d_iso = datetime.strptime(sat['data'], "%d/%m/%Y").date().isoformat()
            except Exception:
                pass
        if d_iso and sat.get('dia_equivalente'):
            sabados_config[d_iso] = sat.get('dia_equivalente')

    # 8. Carregar feriados
    feriados_config = database_model.get_config('feriados.json', PROJECT_ROOT) or {}
    feriados_data = set()
    for categoria in ['ferias_e_recessos', 'feriados_e_datas_importantes', 'planejamento_e_formacao', 'exames']:
        datas = feriados_config.get(categoria, [])
        for item in datas:
            if 'data' in item:
                feriados_data.add(item['data'])
            elif 'inicio' in item and 'fim' in item:
                start = datetime.strptime(item['inicio'], "%Y-%m-%d").date()
                end = datetime.strptime(item['fim'], "%Y-%m-%d").date()
                curr = start
                while curr <= end:
                    feriados_data.add(curr.isoformat())
                    curr += timedelta(days=1)

    # 9. Carregar bloqueios do portal
    blocked_dates = set()
    try:
        cursor.execute("SELECT data, turma_id, disciplina_id FROM blocked_dates")
        for r in cursor.fetchall():
            try:
                blocked_dates.add((str(r['data']), str(r['turma_id']), str(r['disciplina_id'])))
            except:
                pass
    except:
        pass

    # 9b. Carregar data de corte do planejamento
    data_corte = None
    try:
        corte_valor = database_model.get_config('data_corte_planejamento', PROJECT_ROOT)
        if corte_valor:
            data_corte = datetime.strptime(str(corte_valor)[:10], "%Y-%m-%d").date()
    except:
        pass

    # 9b. Carregar max_hours e duration_type por disciplina (do banco de dados)
    # Isso torna o sistema agnóstico - qualquer valor pode ser configurado via admin
    disciplina_max_hours = {}
    disciplina_duration_type = {}
    try:
        cursor.execute("SELECT id, max_hours, duration_type FROM subjects")
        for row in cursor.fetchall():
            disciplina_max_hours[row[0]] = row[1] if row[1] else 40  # default 40
            disciplina_duration_type[row[0]] = row[2] or 'anual'  # default anual
    except:
        disciplina_max_hours = {}
        disciplina_duration_type = {}

    # 9c. Carregar TODAS as configs turma-disciplina (aliases_id)
    # Estrutura: {(turma_id, disciplina_id): config} e {turma_id: config} (uma por turma)
    turma_disc_configs_all = {}
    turma_disc_config_by_turma = {}
    try:
        cursor.execute("""
            SELECT turma_id, disciplina_id, data_inicio, data_fim, aliases_id
            FROM turma_disciplina_config
        """)
        for row in cursor.fetchall():
            cfg = {
                'turma_id': row[0],
                'disciplina_id': row[1],
                'data_inicio': row[2],
                'data_fim': row[3],
                'aliases_id': row[4]
            }
            turma_disc_configs_all[(str(row[0]), str(row[1]))] = cfg
            turma_disc_configs_all[(int(row[0]), int(row[1]))] = cfg
            # Índice por turma: se turma já tem config, não sobrescreve
            if row[0] not in turma_disc_config_by_turma:
                turma_disc_config_by_turma[row[0]] = cfg
            if str(row[0]) not in turma_disc_config_by_turma:
                turma_disc_config_by_turma[str(row[0])] = cfg
    except:
        pass

    # 10. Carregar mappings (bloqueios de grade)
    mappings_cfg = database_model.get_config('mappings.json', PROJECT_ROOT) or {}
    if not isinstance(mappings_cfg, dict):
        mappings_cfg = {}
    blocked_schedules = mappings_cfg.get('blocked_schedules', [])
    if not isinstance(blocked_schedules, list):
        blocked_schedules = []
    completed_subjects_raw = mappings_cfg.get('disciplinas_concluidas', [])
    if isinstance(completed_subjects_raw, list):
        completed_subjects = set(completed_subjects_raw)
    else:
        completed_subjects = set()

    # Carregar max_hours por disciplina (limite absoluto de aulas por disciplina)
    disciplina_max_hours = {}
    try:
        cursor.execute("SELECT id, max_hours FROM subjects")
        for row in cursor.fetchall():
            disciplina_max_hours[row[0]] = row[1] if row[1] else 40  # default 40 if None
    except:
        disciplina_max_hours = {}

    # Contador de aulas GERADAS por disciplina (começa do max_hours e decrementa)
    # Isso respeita o limite absoluto, não importa quantas lessons existam na tabela
    aulas_restantes_por_disc = {}

    # 11. Carregar blacklist de alunos
    blacklist_ras = []
    blacklist_names = []
    exceptions_file = os.path.join(PROJECT_ROOT, "data", "excecoes_alunos.json")
    if os.path.exists(exceptions_file):
        try:
            with open(exceptions_file, 'r', encoding='utf-8') as f:
                exc_data = json.load(f)
                blacklist_ras = [str(r).strip() for r in exc_data.get("blacklist", []) if r]
                blacklist_names = [str(n).upper().strip() for n in exc_data.get("blacklist_names", []) if n]
        except:
            pass

    # --- Contadores por disciplina ---
    next_aula_num = {}  # (turma_code, disciplina_id) → próximo número sequencial

    # Carregar mapeamento de sequência de aulas (se existir)
    sequence_map = {}  # (turma_id, disciplina_id) → {posicao: aula_num}
    try:
        cursor.execute('''CREATE TABLE IF NOT EXISTS aula_sequence_map (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            turma_id TEXT NOT NULL,
                            disciplina_id INTEGER NOT NULL,
                            posicao_historico INTEGER NOT NULL,
                            aula_num INTEGER NOT NULL,
                            observacao TEXT,
                            UNIQUE(turma_id, disciplina_id, posicao_historico))''')

        cursor.execute("""
            SELECT turma_id, disciplina_id, posicao_historico, aula_num
            FROM aula_sequence_map
        """)
        for r in cursor.fetchall():
            tid = str(r['turma_id'])
            did = r['disciplina_id']
            pos = int(r['posicao_historico'])
            a_num = int(r['aula_num'])

            # Registra em todas as variantes de chaves
            for k in [
                (tid, did), (tid, str(did)), (tid, int(did) if str(did).isdigit() else did)
            ]:
                if k not in sequence_map:
                    sequence_map[k] = {}
                sequence_map[k][pos] = a_num

            # Se houver alias associado (ex: did=6 -> 33/34 ou did=33 -> 6)
            for (c_tid, c_did), c_cfg in turma_disc_configs_all.items():
                if str(c_tid) == tid and (str(c_did) == str(did) or str(c_cfg.get('aliases_id')) == str(did)):
                    for extra_k in [
                        (tid, c_did), (tid, str(c_did)), (tid, c_cfg.get('aliases_id')), (tid, str(c_cfg.get('aliases_id')))
                    ]:
                        if extra_k and extra_k not in sequence_map:
                            sequence_map[extra_k] = {}
                        if extra_k:
                            sequence_map[extra_k][pos] = a_num
    except Exception:
        pass  # Tabela pode não existir ainda

    # Inicializar contadores com histórico existente (aulas JÁ registradas no portal)
    # Só linhas canônicas (nome atual da turma) entram na contagem; resíduos de
    # bots antigos inflariam o seq além de max_hours e travariam a geração.
    for (tid, did), (cnt, max_idx) in hist_count.items():
        effective_cnt = max(cnt, max_idx)

        # Registra a contagem em todas as chaves equivalentes
        equivalent_keys = [
            (tid, did),
            (tid, int(did) if did.isdigit() else did)
        ]
        # Propaga para filhas e bases se mapeadas
        for (c_tid, c_did), c_cfg in turma_disc_configs_all.items():
            if str(c_tid) == tid and (str(c_did) == did or str(c_cfg.get('aliases_id')) == did):
                equivalent_keys.extend([
                    (tid, c_did),
                    (tid, str(c_did)),
                    (tid, c_cfg.get('aliases_id')),
                    (tid, str(c_cfg.get('aliases_id')))
                ])

        for key in set(filter(None, equivalent_keys)):
            max_pos = 0
            if key in sequence_map and sequence_map[key]:
                max_pos = max(sequence_map[key].keys())
            next_aula_num[key] = max(next_aula_num.get(key, 0), effective_cnt, max_pos)

    # Inicializar com planejamento pendente.
    # Em modo "Sobrescrever" (force_overwrite), os pendentes existentes serão
    # regenerados e re-numerados a partir do histórico (ordem natural consecutiva),
    # portanto NÃO somam à contagem de partida aqui (IS-019).
    cursor.execute("""
        SELECT turma_id, disciplina_id, COUNT(*) as cnt
        FROM planejamento
        WHERE status IN ('pendente', 'pronta')
        GROUP BY turma_id, disciplina_id
    """)
    if not force_overwrite:
        for r in cursor.fetchall():
            tid = str(r['turma_id'])
            did = str(r['disciplina_id'])
            cnt = int(r['cnt'])
            for key in [(tid, did), (tid, int(did) if did.isdigit() else did)]:
                next_aula_num[key] = next_aula_num.get(key, 0) + cnt

    # --- Regra de inicio: ultima aula registrada (piso: data de corte) ---
    # Sabados letivos seguem apenas a data de corte.
    inicio_map, base_inicio = regras_datas.inicio_geracao(data_corte, data_inicio)

    # Logs de debug
    debug_info = {
        "subjects_count": len(subjects_raw),
        "classes_count": len(classes_raw),
        "grade_count": len(grade_raw),
        "lessons_count": len(lessons_raw),
        "historico_count": len(historico_set),
        "planejamento_count": len(planejamento_set),
        "feriados_count": len(feriados_data),
        "data_inicio": data_inicio.isoformat(),
        "data_fim": data_fim.isoformat(),
        "turmas_ativas": list({g['class_name'] for g in grade_raw}),
        "disciplinas": [{"id": s['id'], "name": s['name']} for s in subjects_raw[:10]],
        "grade_sample": [{"turma": g['class_name'], "dia": g['day_of_week'], "horario": g['time_slot'], "disc": g['subject_name']} for g in grade_raw[:10]],
        "calendario": {"inicio": data_inicio_str, "fim": data_fim_str},
        "data_corte": data_corte.isoformat() if data_corte else None,
        "next_aula_num_sample": {f"{k[0]}_{k[1]}": v for k, v in list(next_aula_num.items())[:5]},
    }

    # --- Geração dos planos ---
    novos_planos = []
    debug_counters = {"turmas_iteradas": 0, "dias_iterados": 0, "slots_processados": 0, "slots_gerados": 0, "slots_pulados": [], "sem_licao": 0, "freq_outra_disciplina": []}

    # Ordenar grade por dia da semana e horário
    grade_ordenada = sorted(grade_raw, key=lambda x: (
        dia_map_rev.get(x['day_of_week'], 99),
        extract_start_time_key_local(x['time_slot']).zfill(4)
    ))

    # --- Filtros opcionais (turma / disciplina) ---
    filtro_turma_nome = None
    if turma_id:
        alvo_norm = normalize_key_local(str(turma_id))
        # aceita code, id ou nome da turma
        filtro_turma_nome = mapa_turmas_norm.get(alvo_norm)
        if not filtro_turma_nome:
            for c in classes_raw:
                if str(c['code']) == str(turma_id) or str(c['id']) == str(turma_id):
                    filtro_turma_nome = c['name']
                    break

    filtro_disc_ids = set()
    if disciplina_id:
        raw_disc = str(disciplina_id).strip()
        if raw_disc.isdigit() and raw_disc in mapa_ids:
            d_info_filtro = mapa_ids[raw_disc]
        else:
            d_info_filtro = resolve_subject_info_local(raw_disc, mapa_disciplinas)
        did_str = str(d_info_filtro['id']) if d_info_filtro else (raw_disc if raw_disc.isdigit() else None)
        if did_str:
            filtro_disc_ids.add(did_str)
            did_int = int(did_str) if did_str.isdigit() else None
            if did_int is not None:
                if did_int in base_to_aliases:
                    filtro_disc_ids.update({str(a) for a in base_to_aliases[did_int]})
                if did_int in alias_to_base:
                    filtro_disc_ids.add(str(alias_to_base[did_int]))
                    base_id = alias_to_base[did_int]
                    if base_id in base_to_aliases:
                        filtro_disc_ids.update({str(a) for a in base_to_aliases[base_id]})
                for (ct, cd), cfg in turma_disc_configs_all.items():
                    if str(cfg.get('aliases_id')) == did_str:
                        filtro_disc_ids.add(str(cd))
                    if str(cd) == did_str and cfg.get('aliases_id'):
                        filtro_disc_ids.add(str(cfg.get('aliases_id')))

    # Iterar sobre turmas
    turmas_ativas = sorted(list({g['class_name'] for g in grade_raw}))
    if filtro_turma_nome:
        turmas_ativas = [t for t in turmas_ativas if t == filtro_turma_nome]

    for nome_turma in turmas_ativas:
        turma_code = mapa_turmas.get(nome_turma)
        if not turma_code:
            debug_counters["slots_pulados"].append(f"Turma '{nome_turma}' sem code mapeado")
            continue
        debug_counters["turmas_iteradas"] += 1

        # Iterar sobre dias do calendário
        curr_date = data_inicio
        while curr_date <= data_fim:
            data_iso = curr_date.isoformat()

            # Pula datas anteriores ao ponto de corte
            if data_corte and curr_date < data_corte:
                curr_date += timedelta(days=1)
                continue

            # Pula feriados, ferias/recessos, planejamento e exames
            # (feriados_data vem do master_config -> feriados.json)
            if data_iso in feriados_data:
                debug_counters["slots_pulados"].append(f"Feriado/recesso: {data_iso}")
                curr_date += timedelta(days=1)
                continue

            # Trata domingos e sábados (sábados só entram se configurados como letivos/reposição)
            if curr_date.weekday() == 6:  # Domingo sempre pula
                curr_date += timedelta(days=1)
                continue

            dia_nome = None
            if curr_date.weekday() == 5:  # Sábado
                dia_nome = sabados_config.get(data_iso)
                if not dia_nome:
                    curr_date += timedelta(days=1)
                    continue
            else:
                dia_nome = dia_map.get(curr_date.weekday())
                if not dia_nome:
                    curr_date += timedelta(days=1)
                    continue

            # Slots do dia para esta turma (dia normalizado: 'Terca' == 'Terça')
            _dia_nome_norm = _norm_dia(dia_nome)
            slots_hoje = [g for g in grade_ordenada
                         if g['class_name'] == nome_turma and _norm_dia(g['day_of_week']) == _dia_nome_norm]

            # Sábados letivos: no máximo 4 aulas por dia (dias úteis: até 8)
            limite_dia = 4 if curr_date.weekday() == 5 else 8
            count_aulas_dia = 0
            debug_counters["dias_iterados"] += 1

            for slot in slots_hoje:
                if count_aulas_dia >= limite_dia:
                    break

                horario = slot['time_slot']
                disciplina_grade = slot['subject_name']
                debug_counters["slots_processados"] += 1

                # Verificar bloqueio de horário
                if any(b.get('day') == dia_nome and b.get('time') == horario
                       for b in blocked_schedules if isinstance(b, dict)):
                    debug_counters["slots_pulados"].append(f"Bloqueio grade: {data_iso} {horario} {disciplina_grade}")
                    continue

                h_key = extract_start_time_key_local(horario).zfill(4)

                # Verificar se slot já está ocupado (histórico ou planejamento)
                if (data_iso, h_key, turma_code) in historico_set:
                    debug_counters["slots_pulados"].append(f"Ja existe no historico: {data_iso} {h_key} {turma_code}")
                    continue
                if (data_iso, h_key, turma_code) in planejamento_set and not force_overwrite:
                    debug_counters["slots_pulados"].append(f"Ja existe no planejamento: {data_iso} {h_key} {turma_code}")
                    continue

                # Resolver disciplina real
                gn = normalize_key_local(disciplina_grade)
                is_generic = disciplina_grade.strip() in GENERIC_LABELS

                # Inicializar restricoes globais (serao usadas se nao houver configuracao turma-especifica)
                restricoes_global = calendario.get('restricoes_planejamento', {})

                disc_id = None
                disc_name = disciplina_grade

                if is_generic:
                    # Resolver "Disc.Tec." via configuração mensal do settings
                    disc_mensal = turma_to_monthly.get(turma_code)
                    if disc_mensal:
                        d_info = resolve_subject_info_local(disc_mensal, mapa_disciplinas)
                        if d_info:
                            disc_id = d_info['id']
                            disc_name = d_info['name']
                    
                    if not disc_id:
                        # Fallback: usar fila de modulares
                        turma_disc_config = turma_disc_config_by_turma.get(turma_code)
                        if turma_disc_config and turma_disc_config.get('data_inicio') and turma_disc_config.get('data_fim'):
                            restricoes_usadas = {
                                turma_disc_config['data_inicio']: {'data_fim': turma_disc_config['data_fim']}
                            }
                        else:
                            restricoes_usadas = restricoes_global

                        mod_name, d_info = get_next_modular_subject(
                            restricoes_usadas,
                            next_aula_num, mapa_disciplinas,
                            data_iso, turma_code, turma_to_monthly
                        )
                        if d_info:
                            disc_id = d_info['id']
                            disc_name = d_info['name']
                else:
                    # Resolução direta para disciplinas não-genéricas
                    d_info = resolve_subject_info_local(disciplina_grade, mapa_disciplinas)
                    if d_info:
                        disc_id = d_info['id']
                        disc_name = d_info['name']

                if not disc_id:
                    continue

                # Busca alias correspondente a esta turma e disciplina
                cfg_alias = (
                    turma_disc_configs_all.get((str(turma_code), str(disc_id)))
                    or turma_disc_configs_all.get((int(turma_code) if str(turma_code).isdigit() else turma_code, int(disc_id) if str(disc_id).isdigit() else disc_id))
                    or turma_disc_config_by_turma.get(turma_code)
                    or turma_disc_config_by_turma.get(str(turma_code))
                    or {}
                )
                alias_id = cfg_alias.get('aliases_id')

                # ── Filtro por disciplina ──
                if filtro_disc_ids:
                    alias_disc_id = str(alias_id or '')
                    if str(disc_id) not in filtro_disc_ids and alias_disc_id not in filtro_disc_ids:
                        continue

                # Regra de data: dias uteis comecam apos a ultima aula registrada
                # (piso: data de corte). Sabados letivos seguem apenas a data de corte.
                if curr_date.weekday() != 5:
                    if curr_date < regras_datas.inicio_disciplina(inicio_map, base_inicio, turma_code, disc_id, alias_id):
                        continue

                # Verificar bloqueio do portal
                if (data_iso, turma_code, str(disc_id)) in blocked_dates:
                    continue

                # Número sequencial no portal iSeduc
                key_cont = (str(turma_code), disc_id)
                current_count = (
                    next_aula_num.get((str(turma_code), disc_id))
                    or next_aula_num.get((str(turma_code), str(disc_id)))
                    or (next_aula_num.get((str(turma_code), int(alias_id))) if alias_id else 0)
                    or (next_aula_num.get((str(turma_code), str(alias_id))) if alias_id else 0)
                    or 0
                )
                seq_num = current_count + 1

                # Atualiza contadores equivalentes
                next_aula_num[(str(turma_code), disc_id)] = seq_num
                next_aula_num[(str(turma_code), str(disc_id))] = seq_num
                if alias_id:
                    next_aula_num[(str(turma_code), int(alias_id))] = seq_num
                    next_aula_num[(str(turma_code), str(alias_id))] = seq_num

                # Verificar limite estrito de carga horária da disciplina (subjects.max_hours)
                max_hours_disc = (
                    disciplina_max_hours.get(disc_id)
                    or (disciplina_max_hours.get(int(alias_id)) if alias_id and str(alias_id).isdigit() else None)
                    or 40
                )

                # Se já atingiu a carga horária máxima da disciplina, não gera mais aulas
                if seq_num > max_hours_disc:
                    continue

                # Filtro opcional de intervalo de aulas a gerar
                if aula_min is not None and aula_min > 0 and seq_num < aula_min:
                    continue
                if aula_max is not None and aula_max > 0 and seq_num > aula_max:
                    continue

                # ID interno para lessons
                internal_disc_id = disc_id
                if str(disc_id) in ('6', '33', '34') or str(cfg_alias.get('aliases_id')) == '6':
                    if str(turma_code) == '309197':
                        internal_disc_id = 33
                    elif str(turma_code) == '314114':
                        internal_disc_id = 34

                # Determina a lição pedagógica: se mapeada no sequence_map usa o marco, senão usa cálculo sequencial
                key_alias_seq = (turma_code, cfg_alias.get('aliases_id') or disc_id)
                mapped_pedag = (
                    sequence_map.get(key_cont, {}).get(seq_num)
                    or sequence_map.get(key_alias_seq, {}).get(seq_num)
                )

                if mapped_pedag:
                    pedagogical_idx = mapped_pedag
                else:
                    pedagogical_idx = seq_num

                # Buscar conteúdo pedagógico
                lessons_list = lessons_by_subject.get(internal_disc_id) or lessons_by_subject.get(disc_id, [])
                lesson = None
                if 0 < pedagogical_idx <= len(lessons_list):
                    _candidata = lessons_list[pedagogical_idx - 1]
                    # Só planeja lessons com título "Aula XX"; lessons sem essa
                    # estrutura (fragmentos/placeholders) ficam fora da fila.
                    if _eh_lesson_planejavel(_candidata.get('title')):
                        lesson = _candidata

                # Se não tem lição em lessons:
                # Se for para a pasta 'prontas', NUNCA salva em prontas sem lição!
                if not lesson:
                    debug_counters["sem_licao"] += 1
                    debug_counters["slots_pulados"].append(f"Sem lição: {disc_name} #{pedagogical_idx}")
                    if output_dir == 'prontas':
                        continue

                title = lesson['title'] if lesson else f"{disc_name} - Aula {pedagogical_idx}"
                desc = (lesson['description'] if lesson else '') or "Continuidade do conteúdo pedagógico anterior."
                video_url = lesson.get('video_url', '') if lesson else ''

                # O número de registro no portal é o seq_num (posição no portal)
                aula_num = seq_num

                # Parse do markdown para extrair secoes estruturadas
                parsed = parse_lesson_markdown((lesson or {}).get('description', ''))
                conteudo_section = parsed.get('conteudo', '') if parsed else ''
                objetivos_list = parsed.get('objetivos', []) if parsed else []
                recursos_section = parsed.get('recursos', '') if parsed else ''
                atividade_section = parsed.get('atividade', '') if parsed else ''

                # Limpar nome da disciplina: remover sufixos como "2026A", "(Turma...)"
                disc_name_clean = re.sub(r'\s*\d{4}[A-Z]\b', '', disc_name)
                disc_name_clean = re.sub(r'\s*\(.*?\)\s*$', '', disc_name_clean).strip()

                plano = {
                    'turma': nome_turma,
                    'turma_id': turma_code,
                    'disciplina': disc_name_clean,
                    'disciplina_id': disc_id,  # ID filho (33 ou 34) para uso interno
                    'aliases_id': cfg_alias.get('aliases_id'),  # ID base (6) para o portal
                    'data': data_iso,
                    'horario': horario,
                    'aula_num': aula_num,
                    'conteudo': clean_text_local(title, 100),
                    'conteudo_descricao': _montar_conteudo_enriquecido(title, objetivos_list, conteudo_section, desc),
                    'objetivos': objetivos_list,
                    'recursos': clean_text_local(recursos_section, 300) if recursos_section else '',
                    'atividade': clean_text_local(atividade_section, 300) if atividade_section else '',
                    'estrategia': estrategia or "Aula expositiva e prática.",
                    'file_suffix': "",
                    'video_url': video_url,
                    'disciplina_nome_display': cfg_alias.get('aliases_name') or re.sub(r'\s*\((?:Prática|Pratica|Teoria|Teórica|Turma.*?)\)', '', re.sub(r'\s*\d{4}[A-Z]\b', '', disc_name), flags=re.IGNORECASE).strip()
                }
                novos_planos.append(plano)
                count_aulas_dia += 1

            curr_date += timedelta(days=1)

    # --- Salvar arquivos .txt ---
    generated_files = []
    skipped_files = []
    deleted_old = []
    planos_com_frequencia = 0
    planos_freq_outra_disciplina = 0
    planos_atualizados_db = 0

    # Limpar arquivos anteriores ao corte (se force_overwrite)
    if data_corte and force_overwrite:
        for fname in os.listdir(output_path):
            if not fname.startswith("plano_") or not fname.endswith(".txt"):
                continue
            # Extrair data do nome: plano_{tid}_{did}_{YYYY-MM-DD}_{horario}.txt
            parts = fname.replace(".txt", "").split("_")
            if len(parts) >= 4:
                try:
                    file_date = datetime.strptime(parts[3], "%Y-%m-%d").date()
                    if file_date < data_corte:
                        os.remove(os.path.join(output_path, fname))
                        deleted_old.append(fname)
                except (ValueError, IndexError):
                    pass

    for p in novos_planos:
        safe_horario = re.sub(r'[^a-zA-Z0-9]', '', p['horario'])
        # Usa aliases_id (ID base: 6) para o nome do arquivo e conteúdo do portal
        txt_disc_id = p.get('aliases_id') or p['disciplina_id']
        fname = f"plano_{p['turma_id']}_{txt_disc_id}_{p['data']}_{safe_horario}{p.get('file_suffix', '')}.txt"
        filepath = os.path.join(output_path, fname)

        # Pular se já existe (proteção de edição manual)
        if os.path.exists(filepath) and not force_overwrite:
            skipped_files.append(fname)
            continue

        # Buscar alunos para frequência
        students = []
        try:
            students = database_model.get_students_by_class_id(p['turma_id'], PROJECT_ROOT)
        except:
            pass

        # Filtrar apenas alunos que não existem no iSeduc (Aluno Teste, Fabiano, inativos)
        def _should_ignore_student(s):
            ra_s = str(s.get('student_number', s.get('username', ''))).strip()
            n_s = (s.get('student_name', s.get('name', '')) or '').strip().upper()
            if "TESTE" in n_s or "TEST " in n_s or n_s.startswith("TEST"):
                return True
            if "FABIANO" in n_s:
                return True
            if s.get('status') == 'inactive':
                return True
            return False

        if students:
            students = [s for s in students if not _should_ignore_student(s)]

        # Montar conteúdo do .txt
        lines = []
        lines.append(f"# PLANO PREENCHIDO")
        lines.append(f"TURMA_ID: {p['turma_id']}")
        lines.append(f"DISCIPLINA_ID: {txt_disc_id}")
        lines.append(f"DATA: {p['data']}")
        lines.append(f"HORARIO: {normalize_horario_range(p['horario'])}")
        lines.append(f"AULA_NUM: {p['aula_num']:02d}")
        lines.append(f"DISCIPLINA_NOME: {p.get('disciplina_nome_display', p['disciplina'])}")
        lines.append("")

        # [CONTEUDO] - usa conteudo_descricao (description da aula) ou titulo como fallback
        lines.append(f"[CONTEUDO]")
        conteudo_txt = p.get('conteudo_descricao', '') or p['conteudo']
        lines.append(f"{conteudo_txt}")
        lines.append("")

        # [ESTRATEGIA]
        lines.append(f"[ESTRATEGIA]")
        lines.append(f"{p['estrategia']}")
        lines.append("")

        # [PLANO_DE_AULA] - usa objetivos reais do markdown ou fallback generico
        lines.append(f"[PLANO_DE_AULA]")
        lines.append(f"### Objetivos da Aula")
        objetivos = p.get('objetivos', [])
        if objetivos:
            for obj in objetivos:
                lines.append(f"- {obj}")
        else:
            lines.append(f"- Apresentar os conceitos fundamentais de {p['disciplina']}.")
            lines.append(f"- Desenvolver habilidades práticas em {p['disciplina']}.")
            lines.append(f"- Promover a discussão e o pensamento crítico sobre o tema da aula.")
        # Adicionar atividade se disponivel
        atividade = p.get('atividade', '')
        if atividade:
            lines.append("")
            lines.append(f"### Atividade")
            lines.append(f"{atividade}")
        lines.append("")

        freq_linhas = []
        att_source = None
        att_diag = {}
        lines.append(f"[FREQUENCIA]")
        lines.append(f"### Lista de Presença")
        if students:
            # Busca frequencia REAL pela DATA EXATA da aula.
            # Prioridade: exceções manuais -> tabela attendance (com fallback de
            # outra disciplina) -> corrigido -> normalizado -> raw -> planejado.
            turma_code = str(p['turma_id'])
            disc_id = str(p['disciplina_id'])
            attendance_map, att_source, att_diag = banco.load_attendance_map_for(turma_code, disc_id, p['data'])

            for student in students:
                name = student.get('student_name', '')
                ra = str(student.get('student_number', student.get('username', ''))).strip()
                name_upper = name.upper().strip()

                # REGRA ABSOLUTA: Alunos na blacklist SEMPRE recebem Falta
                is_blacklisted = (
                    ra in blacklist_ras
                    or any(bn in name_upper or name_upper in bn for bn in blacklist_names)
                )

                if is_blacklisted:
                    status = "Falta"
                elif ra in attendance_map:
                    status = attendance_map[ra]
                elif name in attendance_map:
                    status = attendance_map[name]
                else:
                    status = "Presente"  # Default para aulas futuras
                lines.append(f"- {name}: {status}")
                freq_linhas.append(f"- {name}: {status}")
        else:
            lines.append(f"- Nenhuma lista de alunos disponível para esta turma.")
        frequencia_texto = "\n".join(freq_linhas)
        lines.append("")
        lines.append(f"[RECURSOS_DIDATICOS]")
        lines.append(f"### Recursos Utilizados")
        # Titulo: disciplina + numero da aula
        lines.append(f"- Título: {p['disciplina']} - Aula {p['aula_num']:02d}")
        if p.get('video_url'):
            lines.append(f"- Link: {p['video_url']}")
        # Comentario: usa recursos do markdown ou estrategia como fallback
        recursos_txt = p.get('recursos', '') or p['estrategia']
        lines.append(f"- Comentário: {recursos_txt}")

        # Salvar arquivo
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        generated_files.append(fname)
        if att_source:
            planos_com_frequencia += 1
        if att_diag.get("outra_disciplina"):
            planos_freq_outra_disciplina += 1
            debug_counters["freq_outra_disciplina"].append(
                f"{fname}: {att_source}")

        # Salvar/atualizar no banco (planejamento) - upsert: nunca duplica slot
        try:
            conn = banco.get_db_connection()
            cursor = conn.cursor()
            campos = {
                'turma': p['turma'],
                'disciplina': p['disciplina'],
                'data_planejada': p['data'],
                'horario': p['horario'],
                'numero_aula': str(p['aula_num']),
                'status': 'pendente',
                'turma_id': str(p['turma_id']),
                'disciplina_id': str(p['disciplina_id']),
                'conteudo_abordado': p.get('conteudo_descricao', '') or p.get('conteudo', ''),
                'estrategia': p.get('estrategia', ''),
                'recursos_titulo': f"{p['disciplina']} - Aula {p['aula_num']:02d}",
                'recursos_link': p.get('video_url', ''),
                'recursos_comentario': p.get('recursos', '') or p.get('estrategia', ''),
                'atividade': p.get('atividade', ''),
                'frequencia': frequencia_texto,
            }
            # Em modo "Sobrescrever", apagar linhas antigas do MESMO slot com
            # numeração divergente (a nova numeração substitui a antiga, sem resíduo).
            if force_overwrite:
                cursor.execute("""
                    DELETE FROM planejamento
                    WHERE turma_id = ? AND disciplina_id = ? AND data_planejada = ? AND horario = ?
                      AND numero_aula != ?
                """, (campos['turma_id'], campos['disciplina_id'], campos['data_planejada'],
                      campos['horario'], campos['numero_aula']))
            existente = cursor.execute("""
                SELECT id FROM planejamento
                WHERE turma_id = ? AND disciplina_id = ? AND data_planejada = ? AND horario = ?
                  AND COALESCE(numero_aula,'') = ?
                LIMIT 1
            """, (campos['turma_id'], campos['disciplina_id'], campos['data_planejada'],
                  campos['horario'], campos['numero_aula'])).fetchone()
            if existente:
                sets = ', '.join(f"{k} = ?" for k in campos)
                cursor.execute(
                    f"UPDATE planejamento SET {sets} WHERE id = ?",
                    list(campos.values()) + [existente['id']],
                )
                planos_atualizados_db += 1
            else:
                cols = ', '.join(campos.keys())
                placeholders = ', '.join(['?'] * len(campos))
                cursor.execute(
                    f"INSERT INTO planejamento ({cols}) VALUES ({placeholders})",
                    list(campos.values()),
                )
            conn.commit()
            conn.close()
        except Exception as e:
            debug_counters["slots_pulados"].append(f"Erro persistindo plano {fname}: {e}")

    # --- Gerar logs de aulas ---
    logs_gerados = {}
    try:
        # Agrupar planos por turma/disciplina para gerar logs
        planos_por_turma_disc = {}
        for p in novos_planos:
            key = (p['turma_id'], p['disciplina_id'])
            if key not in planos_por_turma_disc:
                planos_por_turma_disc[key] = []
            planos_por_turma_disc[key].append(p)
        
        # Gerar log para cada turma/disciplina
        for (turma_id, disc_id), planos in planos_por_turma_disc.items():
            lessons_data = []
            for p in sorted(planos, key=lambda x: x['aula_num']):
                lessons_data.append({
                    'aula_num': p['aula_num'],
                    'titulo': p.get('conteudo', ''),
                    'data': p['data'],
                    'hora': p['horario'],
                    'conteudo': p.get('conteudo_descricao', '') or p.get('conteudo', '')
                })
            
            log_result = generate_lesson_log(
                turma_id=turma_id,
                disciplina_id=str(disc_id),
                lessons_data=lessons_data
            )
            logs_gerados[f"{turma_id}_{disc_id}"] = log_result
    except Exception as e:
        debug_counters["slots_pulados"].append(f"Erro gerando logs: {e}")

    return {
        "status": "success",
        "message": f"{len(generated_files)} planos gerados em {output_path}" + (f", {len(deleted_old)} antigos removidos" if deleted_old else ""),
        "generated": len(generated_files),
        "skipped": len(skipped_files),
        "deleted_old": len(deleted_old),
        "com_frequencia": planos_com_frequencia,
        "freq_outra_disciplina": planos_freq_outra_disciplina,
        "updated_db": planos_atualizados_db,
        "sem_licao": debug_counters["sem_licao"],
        "path": f"aulas/{output_dir}/",
        "files": generated_files,
        "skipped_files": skipped_files,
        "logs_gerados": logs_gerados,
        "debug": debug_info,
        "counters": debug_counters
    }
