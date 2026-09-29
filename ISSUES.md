# 📋 Issues do repositório syava-apps

Registro local dos problemas e melhorias dos apps Streamlit deste repositório.
IDs próprios **`AP-NNN`** (não confundir com os `IS-NNN` do SysAva).

Símbolos: 🟢 concluído · 🟡 em andamento · 🔴 pendente · ⚪ cancelado

---

## Índice

| ID | Título | Status | Data |
|---|---|---|---|
| AP-001 | Down SeducTec: app de download de PDFs e links de vídeo (porta 8504) | 🟢 | 2026-09-29 |
| AP-002 | Criação do repositório syava-apps (repo aninhado em `apps/`, docs e bootloader) | 🟢 | 2026-09-29 |

---

## AP-001 — Down SeducTec: app de download de PDFs e links de vídeo 🟢

**Pedido:** baixar as aulas do portal SeducTec (PDFs + links de vídeo)
organizadas por semana, integradas à estrutura do SysAva.

**Solução:**
- `down_seductec/seductec_downloader.py` — núcleo portado do script legado
  `Aulas_selenium/tools/utils/seductec_scraper.py`: login manual no Chrome
  detectado por polling (sem `input()`), extração dos tiles `S(\d+)-AULA\s*(\d+)`,
  download de PDFs resolvendo os redirects do Moodle (`pluginfile.php` /
  `forcedownload=1`), coleta de links YouTube e `links_aulas.md` **reescrito por
  execução** (idempotente; o legado duplicava em reexecuções).
- `down_seductec/down_seductec_streamlit.py` — UI na porta **8504** com
  `st.fragment(run_every=1)` para log/progresso ao vivo, thread única por
  download, turma vinda de `db.get_classes()` e mapeamento do nome do portal
  para a pasta existente via `suggest_disciplina()`.
- Destino: `data/repo/<turma>/<disciplina>/<S0X>/seductec/` (compatível com o
  `generate_lessons_gemini`, que procura `data/repo/<turma>/<disciplina>/S0X/`).

**Arquivos:** `apps/down_seductec/*`, `apps/run_apps.bat`, `run.bat` (SysAva).

**Validação:** `py_compile` OK; app sobe na 8504 e renderiza (sidebar com turma,
log ao vivo, botão Conectar); caminho de destino gerado corretamente. Download
real depende de login manual no portal (validação manual).

---

## AP-002 — Criação do repositório syava-apps 🟢

**Pedido:** separar os apps Streamlit em um repositório GitHub próprio, com
README, ISSUES, AGENTS e bootloader próprios, mantendo o `run.bat` do SysAva
apontando para eles.

**Solução:**
- Repo **aninhado** em `apps/` (`git init` local + remote
  `https://github.com/hiseg10/syava-apps`). O SysAva continua ignorando
  `apps/` (`.gitignore` linha 34), então não há conflito entre os dois repos.
- `apps/.gitignore` exclui fora de escopo: `api/`, `apis_gemini_key/`,
  `data/`, backups `.db`, `.csv`, `html/`, logs, `.chrome_profile/`.
- Docs próprios: `README.md`, `ISSUES.md` (este arquivo), `AGENTS.md`,
  `requirements.txt` e o bootloader `run_apps.bat`.
- `run.bat` do SysAva ganhou as entradas dos apps e o link do repositório.

**Arquivos:** `apps/{README.md,ISSUES.md,AGENTS.md,.gitignore,requirements.txt,run_apps.bat}`,
`run.bat`, `docs/ISSUES_LOCAIS.md` (IS-036).

**Validação:** `git status` em `apps/` não lista nenhum dado sensível;
scan por chaves/segredos limpo; menu do `run.bat` atualizado (1-8).

---

## Comandos úteis

```bat
:: Iniciar apps pelo bootloader do repositório
apps\run_apps.bat

:: Subir só o Down SeducTec
.sysenv\Scripts\streamlit.exe run apps/down_seductec/down_seductec_streamlit.py --server.port 8504
```
