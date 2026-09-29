# 🤖 Instruções para Agentes — syava-apps (repo aninhado em `SysAva/apps/`)

Este repositório contém os apps Streamlit auxiliares do SysAva. **Leia antes
de modificar qualquer coisa.**

---

## 🏗️ Contexto obrigatório

- Repo **aninhado**: vive em `SysAva/apps/` e **não é standalone**. Os apps
  importam `services.*` e `apps/api/tools/*` da raiz do SysAva.
- Ambiente virtual único: `SysAva/.sysenv` (Python 3.11). Nunca crie outro venv
  aqui; se `apps/.venv` aparecer, apague.
- O SysAva ignora `apps/` no `.gitignore` dele — os dois repos não conflitam.
  **Nunca** faça `git add` da raiz do SysAva esperando versionar estes arquivos.

## 📁 Escopo versionado

Versionado: `duplicate_checker/`, `supabase_monitor/`,
`planejamento_registro/`, `analise_notas/`, `down_seductec/`, `__init__.py`,
docs (`README.md`, `ISSUES.md`, `AGENTS.md`, `requirements.txt`,
`run_apps.bat`, `.gitignore`).

**Nunca versionar** (bloqueado pelo `.gitignore`): `api/`, `apis_gemini_key/`,
`data/`, `*.db`, `*.csv`, `logs/`, `html/`, PDFs, `.chrome_profile/`,
`.env`, `secrets.toml`, `__pycache__/`.

> ⚠️ Repo **público**: proibido commitar chaves, tokens, `secrets.toml`,
> backups de banco ou dados de alunos (nomes, notas, frequência).

## 🚀 Portas fixas (não mudar)

| App | Porta |
|---|---|
| `duplicate_checker` | 8502 |
| `supabase_monitor` | 8503 |
| `down_seductec` | 8504 |
| `planejamento_registro` | 8510 |

A porta 8501 pertence à aplicação principal do SysAva (`app.py`).

## 📝 Convenções

1. **`sys.path`** — todo módulo que importar `services.*` precisa inserir a raiz
   do SysAva antes (3x `dirname` a partir do arquivo em `apps/<app>/`).
2. **Caching** — leituras repetitivas de Supabase devem usar
   `services/local_cache.py` (regra de egress do SysAva).
3. **Selenium** — só em `down_seductec`; nunca bloquear a thread principal do
   Streamlit (usar `threading.Thread` + `st.fragment(run_every=...)`), e nunca
   usar `input()`/`print()` no código do app (usar callbacks de log).
4. **Português** — UI, comentários e docs em português.

## 🗂️ Registro de issues (obrigatório)

- Toda alteração relevante deve ser registrada em **[`ISSUES.md`](ISSUES.md)**
  com o próximo ID **`AP-NNN`** (formato 🟢/🟡/🔴, arquivos afetados, validação).
- Correções que afetem o núcleo do SysAva também vão em
  `SysAva/docs/ISSUES_LOCAIS.md` como `IS-NNN`.
