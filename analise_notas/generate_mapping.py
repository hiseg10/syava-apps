"""
Gera o mapeamento.json a partir do backup do banco SQLite do SysAva.

Extrai:
  - Turmas (classes)
  - Disciplinas (subjects) - separa em oficiais e informais
  - Relação turma × disciplina (class_subjects) - apenas as ativas
"""
import json
import os
import sqlite3

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'data', 'repo', 'plugins', 'backup_SysAva_2026-09-08.db'
)
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'html', 'mapeamento.json'
)

# Siglas conhecidas (para encurtar labels)
SIGLAS = {
    '1':  'P.C.II',
    '2':  'Ment.Tec.II',
    '3':  'P.E.',
    '4':  'POO',
    '5':  'Disp.Móv.',
    '6':  'Web FE',
    '7':  'Arq.MS',
    '8':  'UI/UX',
    '9':  'DevOps',
    '10': 'Man.Sis.',
    '11': 'I.A.',
    '30': 'POO I-A',
    '31': 'Web FE I-B',
    '33': 'Web FE 26A',
    '34': 'Web FE 26B',
    '35': 'Caderno',
}


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1) Turmas
    cur.execute("SELECT id, name, code, official_name FROM classes ORDER BY id")
    turmas = []
    for tid, name, code, official in cur.fetchall():
        turmas.append({
            'id': str(tid),
            'nome': name,
            'nome_curto': f"Turma {name.split('Turma ')[-1].split(' ')[0]}" if 'Turma ' in name else name,
            'codigo': code,
            'nome_oficial': official,
        })

    # 2) Disciplinas - separar em oficiais e informais
    cur.execute("SELECT id, name FROM subjects ORDER BY id")
    oficiais, informais = [], []
    for sid, name in cur.fetchall():
        sid_s = str(sid)
        # Disciplinas "formais" tem id 1-11 (base curricular)
        # Disciplinas "informais" tem id >= 30 (variantes por turma/ano)
        is_informal = int(sid) >= 30
        entry = {
            'id': sid_s,
            'nome': name,
            'sigla': SIGLAS.get(sid_s, sid_s),
        }
        if is_informal:
            # Tenta extrair o vínculo com turma do nome
            vinculo = None
            if 'Turma I-A' in name:
                vinculo = '1'
            elif 'Turma I-B' in name:
                vinculo = '2'
            if vinculo:
                entry['vinculo_turma'] = vinculo
            informais.append(entry)
        else:
            oficiais.append(entry)

    # 3) Relação turma × disciplina (apenas ativas)
    cur.execute("""
        SELECT class_id, subject_id, id, is_active
        FROM class_subjects
        ORDER BY class_id, subject_id
    """)
    relacoes = []
    turma_disc = {}  # {turma_id: [disciplina_ids]}
    for cid, sid, rid, active in cur.fetchall():
        relacoes.append({
            'turma_id': str(cid),
            'subject_id': str(sid),
            'id': str(rid),
            'is_active': str(active),
        })
        if str(active) == '1':
            turma_disc.setdefault(str(cid), []).append(str(sid))

    # Monta turma_disciplina com base nas relações ativas
    turma_disciplina = []
    for tid in sorted(turma_disc.keys()):
        discs = sorted(turma_disc[tid], key=lambda x: int(x))
        turma_disciplina.append({
            'turma_id': tid,
            'disciplina_ids': discs,
            'total': len(discs),
        })

    conn.close()

    # Monta o JSON final
    output = {
        '_comentario': 'Gerado a partir de backup_SysAva_2026-09-08.db (tabelas: classes, subjects, class_subjects).',
        'turmas': turmas,
        'disciplinas_oficiais': oficiais,
        'disciplinas_informais': informais,
        'turma_disciplina': turma_disciplina,
        'relacoes_completas': relacoes,
    }

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'✅ Mapeamento gerado: {OUTPUT_PATH}')
    print(f'   Turmas: {len(turmas)}')
    print(f'   Disciplinas oficiais: {len(oficiais)}')
    print(f'   Disciplinas informais: {len(informais)}')
    print(f'   Relações ativas: {sum(1 for r in relacoes if r["is_active"] == "1")}')
    print()
    print('=== DISCIPLINAS POR TURMA (apenas ativas) ===')
    for td in turma_disciplina:
        tid = td['turma_id']
        turma_nome = next(t['nome'] for t in turmas if t['id'] == tid)
        discs_nomes = []
        for did in td['disciplina_ids']:
            d = next((x for x in oficiais + informais if x['id'] == did), None)
            if d:
                discs_nomes.append(f"{d['sigla']}({did})")
        print(f'  Turma {tid} ({turma_nome}):')
        print(f'    {", ".join(discs_nomes)}')
        print(f'    Total: {td["total"]} disciplinas')


if __name__ == '__main__':
    main()