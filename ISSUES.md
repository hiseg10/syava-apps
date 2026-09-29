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
| AP-005 | Planejamento: feriados do `master_config` não bloqueavam geração/registro de aulas | 🟢 | 2026-09-29 |
| AP-006 | Planejamento: migração de `planejamento_config` para `master_config` e DROP da tabela | 🟢 | 2026-09-29 |
| AP-007 | Planejamento: frequência ao vivo com diagnóstico, fallback de outra disciplina e exceções manuais | 🟢 | 2026-09-29 |

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

## AP-005 — Planejamento: feriados não bloqueavam geração/registro 🟢

**Sintoma:** aulas eram geradas e registradas em datas de feriado (ex.:
07/09/2026 — Independência; também 12/10, 01/05 etc.).

**Causa raiz:** `core/gerador.py` carregava `feriados_data` do
`master_config` → `feriados.json` (111 datas) mas **só o usava nas
estatísticas** (`feriados_count`). O loop de dias pulava domingos, sábados
não-letivos, `data_corte` e `blocked_dates` — nunca os feriados. E a UI não
tinha nenhum sinal de feriado.

**Solução:**
- `core/gerador.py` — skip no início do loop de dias:
  `if data_iso in feriados_data: ... continue` (com log em `slots_pulados`),
  cobrindo feriados, férias/recessos, planejamento/formação e exames.
- `planejamento_registro_streamlit.py` — helpers `_feriados_config()`
  (cache 300s, mesma fonte do gerador) e `feriado_na_data()` (datas pontuais
  e intervalos `inicio..fim`; aceita `yyyy-mm-dd`/`dd/mm/aaaa`).
- **Bloqueio + aviso** em 🤖 Registrar: planos de feriado ficam fora do
  `multiselect` e fora do "Registrar TODOS" (agora envia a lista filtrada em
  vez de `--all`), com `st.warning` listando os bloqueados.
- **Badges `⚠️ Feriado/recesso`** em: 📄 Planos (visualizador), 👁️ Plano
  Individual e coluna `Feriado` + warning na expander "🗓️ Fila de
  planejamento" (Painel).

**Arquivos:** `apps/planejamento_registro/core/gerador.py`,
`apps/planejamento_registro/planejamento_registro_streamlit.py`,
`apps/ISSUES.md`.

**Validação:** `py_compile` OK; QA no app (8510) com Playwright: badge em
📄 Planos e 👁️ Plano Individual para `2026-09-07` ("Independência do Brasil"),
aviso de bloqueio em 🤖 Registrar com o plano excluído do `multiselect`,
warning "2 plano(s) na fila com data de feriado" no Painel; 0 erros de
console. **Limpeza:** 3 linhas de `planejamento` e 4 `.txt` de feriado
movidos para `data/backup_clean_feriados_20260929_172617/`
(`historico_aulas` intocada — exclusão manual pelo usuário).

---

## AP-006 — Planejamento: `planejamento_config` → `master_config` 🟢

**Sintoma/racional:** as configurações do planejamento viviam na tabela local
`planejamento_config` (`chave/valor`), ausente do `master_config` usado pelo
resto do SysAva (e pelo Supabase) — espelho sem sync e fora do padrão.

**Solução:**
- Migração das 3 chaves para `master_config` como JSON:
  `data_corte_planejamento` (`"2026-04-01"`), `ferias`
  (`"2026-07-13,2026-07-27"`) e `estrategias_disponiveis` (array).
  Script com **backup** `data/escola_ativa_backup_antes_migracao_*.db`,
  verificação via `get_config` e `DROP TABLE planejamento_config`.
- `database_model.set_config(chave, valor, project_root)` novo: JSON encode +
  UPDATE→INSERT, compatível com os schemas `key/value` (real) e `chave/valor`
  (legado do CREATE).
- Consumidores redirecionados: `core/banco.get_config/set_config` (delegam ao
  `database_model`; ganham `listar_parametros()`), `core/gerador.py` (SQL cru
  → `get_config`), `core/datas.data_corte`, UI "Outros parâmetros"
  (`master_config`, lista só chaves não-`.json`), `_estrategias_disponiveis`
  (aceita lista já desserializada) e, fora do app, `apps/api/html_routes.py`
  (leituras + `save-corte`/`save-ferias`) e `apps/api/tools/bot_raspagem.py`.
- `database_model` deixou de criar a tabela antiga; `.gitignore` ganhou
  `data/escola_ativa_backup_*.db`.

**Arquivos:** `apps/planejamento_registro/core/{banco,gerador,datas}.py`,
`apps/planejamento_registro/planejamento_registro_streamlit.py`,
`apps/api/tools/{database_model,bot_raspagem}.py`, `apps/api/html_routes.py`,
`apps/ISSUES.md`.

**Validação:** `py_compile` (7 arquivos) OK; migração executada (3 chaves
verificadas: `str`, `str`, `list`; tabela ausente depois do DROP); aba ⚙️
mostra `Atual: 2026-04-01` e a tabela de parâmetros com as 3 chaves
(`updated_at 2026-09-29 20:11:23`); 0 erros de console.

---

## AP-007 — Planejamento: frequência ao vivo + diagnóstico + fallback 🟢

**Sintoma:** o `.txt` do plano saía com **todos "Presente"** sem aviso quando
a frequência não era encontrada (ex.: registros gravados sob outro
`subject_id`), e a UI não mostrava a frequência real do banco.

**Solução:**
- `core/banco.load_attendance_map_for` agora retorna
  `(mapa, fonte, diagnostico)` com `{encontrou, quantidade, fontes,
  outra_disciplina, disciplina, excecao}`.
- **Fallback de disciplina:** se a turma tem frequência na data gravada sob
  OUTRA disciplina, usa o mapa maior e sinaliza
  `outra_disciplina=True` (tabela `attendance` e JSONs do plugin).
- **Exceções manuais** `data/repo/plugins/attendance_exceptions.json`
  (chave `"{turma}|{data}|{disc}"`): `{"acao": "ignorar"}` ou
  `{"acao": "usar_disciplina", "disciplina": "2", "nota": "..."}`.
- **UI 👁️ Plano individual:** seção "🔎 Frequência ao vivo (banco)" com
  banner ✅ (fonte + quantidade), ⚠️ de outra disciplina, ⚠️ "Nenhuma
  frequência... Consultados: ..." (fallback `Presente` explicado), expander
  com a tabela ao vivo e comparação `.txt` × banco.
- Gerador: inicializa `att_source/att_diag` (evita `NameError` sem alunos),
  reporta `freq_outra_disciplina` (contador + lista em `counters`), UI exibe
  na geração.

**Arquivos:** `apps/planejamento_registro/core/banco.py`,
`apps/planejamento_registro/core/gerador.py`,
`apps/planejamento_registro/planejamento_registro_streamlit.py`,
`apps/ISSUES.md`.

**Validação:** teste unitário — exata `('309197','11','2026-09-28')` → 22
alunos; fallback `('309197','2','2026-09-01')` → 22 alunos de outra disciplina
(`outra_disciplina=True`); sem registro → `{}` com fontes listadas. QA na tela
(8510): banner ✅ 22 no plano 28/09, ⚠️ "Nenhuma frequência" no plano de
feriado 07/09, ⚠️ "outra disciplina (FUNDAMENTOS DE UI / UX OU IHC) — 22" no
plano 01/09; comparação "congelada 20 × ao vivo 22"; 0 erros de console.

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
