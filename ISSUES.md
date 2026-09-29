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
| AP-003 | Down SeducTec: botão "Baixar" permanentemente desabilitado após conectar ao portal | 🟢 | 2026-09-29 |
| AP-004 | Gerador de notebooks `aulas_S0X.ipynb` para as pastas baixadas | 🟢 | 2026-09-29 |

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

## AP-003 — Down SeducTec: botão "Baixar" permanentemente desabilitado após conectar 🟢

**Sintoma:** ao clicar em **Conectar ao portal** e depois listar/selecionar
disciplinas, o botão **Baixar selecionadas** ficava cinza e a UI mostrava
"Download em andamento..." mesmo sem download algum.

**Causa:** o clique em *Conectar* usava a mesma flag `RUNTIME["running"]` do
download e nada a zerava ao terminar de abrir o navegador — o estado
"baixando" ficava preso para sempre.

**Solução:**
- Flag separada `RUNTIME["connecting"]` para a abertura do navegador, com
  `finally` que zera o estado e botão "⏳ Abrindo o navegador..." desabilitado
  durante a conexão.
- `force_logged_in()` passou a usar `check_login_now()` (checagem única, não
  bloqueante) em vez de `wait_for_login(timeout=1)`, eliminando os "Tempo
  esgotado aguardando o login." repetidos a cada segundo no log.
- Barra de progresso só aparece com download ativo; *Listar disciplinas* fica
  desabilitado durante conexão/download.

**Arquivos:** `apps/down_seductec/down_seductec_streamlit.py`,
`apps/down_seductec/seductec_downloader.py`.

**Validação:** conectar → logar → listar → selecionar disciplinas → botão
**Baixar selecionadas** ativo; "Download em andamento..." só durante o job real.

---

## AP-004 — Gerador de notebooks `aulas_S0X.ipynb` 🟢

**Pedido:** gerar um notebook por semana dentro das pastas baixadas pelo Down
SeducTec, com índice navegável e player do YouTube reproduzido no layout
`S0X — AULA NN` + links de Leitura (PDFs).

**Solução:** script standalone `apps/down_seductec/gerar_notebooks.py`:
- Varre `data/repo/<turma>/<disciplina>/S0X/seductec/` (filtros opcionais
  `--turma`, `--disciplina`, `--semanas`) onde houver `links_aulas.md`.
- Reusa `SeductecDownloader._parse_links_md` (parser único de vídeos) e cruza
  com os PDFs `Aula_NN_Parte_*.pdf` locais por aula.
- Gera `aulas_S0X.ipynb` (nbformat v4, `validate()` em cada arquivo):
  célula de índice com âncoras + cartão por aula (PDFs como "📄 Leitura Aula
  NN") + célula de código com `IFrame` do `youtube.com/embed/<id>` e **output
  já embutido** (abre sem rodar nada).
- Assina com `NotebookNotary` (melhor esforço) para o HTML renderizar sem
  "Trust".

**Uso:** `.sysenv\Scripts\python.exe apps\down_seductec\gerar_notebooks.py`
(idempotente — sobrescreve os notebooks).

**Arquivos:** `apps/down_seductec/gerar_notebooks.py`, `apps/ISSUES.md`.

**Validação:** 6 notebooks gerados (S01–S06 de DISPOSITIVOS MÓVEIS; as pastas
POO sob `repo/Turmas/` não têm `links_aulas.md` e ficam de fora); cada um com
`nbformat.validate` OK, 9 células markdown + 8 código, 8 iframes com 8 IDs
YouTube únicos, 8 links de PDF e `check_signature()=True`; prévia HTML
renderizada com os players carregando (0 erros de console).

---

## Comandos úteis

```bat
:: Iniciar apps pelo bootloader do repositório
apps\run_apps.bat

:: Subir só o Down SeducTec
.sysenv\Scripts\streamlit.exe run apps/down_seductec/down_seductec_streamlit.py --server.port 8504

:: Gerar/regaer os notebooks aulas_S0X.ipynb nas pastas baixadas
.sysenv\Scripts\python.exe apps\down_seductec\gerar_notebooks.py
.sysenv\Scripts\python.exe apps\down_seductec\gerar_notebooks.py --semanas S06 --disciplina "PROGRAMAÇÃO PARA DISPOSITIVOS MÓVEIS"
```
