"""Inspeciona o banco SQLite de backup do SysAva."""
import sqlite3
import os

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'data', 'repo', 'plugins', 'backup_SysAva_2026-09-08.db'
)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Lista tabelas
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
print('Tabelas no banco:')
for t in tables:
    cur.execute(f"SELECT COUNT(*) FROM \"{t}\"")
    count = cur.fetchone()[0]
    print(f'  - {t} ({count} registros)')

print()
print('=' * 70)
print('CLASSES (turmas)')
print('=' * 70)
try:
    cur.execute('SELECT * FROM classes LIMIT 5')
    cols = [d[0] for d in cur.description]
    print('Colunas:', cols)
    for row in cur.fetchall():
        print(' ', row)
except Exception as e:
    print('Erro:', e)

print()
print('=' * 70)
print('SUBJECTS (disciplinas)')
print('=' * 70)
try:
    cur.execute('SELECT * FROM subjects LIMIT 20')
    cols = [d[0] for d in cur.description]
    print('Colunas:', cols)
    for row in cur.fetchall():
        print(' ', row)
except Exception as e:
    print('Erro:', e)

print()
print('=' * 70)
print('CLASS_SUBJECTS (relacao)')
print('=' * 70)
try:
    cur.execute('SELECT * FROM class_subjects LIMIT 30')
    cols = [d[0] for d in cur.description]
    print('Colunas:', cols)
    for row in cur.fetchall():
        print(' ', row)
except Exception as e:
    print('Erro:', e)

conn.close()