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
| AP-008 | Planejamento: aba Consolidadas (carga × fluxo anual por turma) + Gantt das janelas do fluxo letivo | 🟢 | 2026-09-29 |
| AP-009 | Planejamento: exclusão em lote de planos na página Planos (seletor multiselect + confirmação) | 🟢 | 2026-09-30 |
| AP-010 | Planejamento: editor da tabela `master_config` na página Config + bloqueio de sábados letivos na geração automática | 🟢 | 2026-09-30 |
| AP-012 | Planejamento: reconciliação do `historico_aulas` com o portal iSeduc (checkbox + aviso de órfãs) | 🟢 | 2026-10-01 |
| AP-013 | Planejamento (IS-042): base da numeração por `MAX(numero_aula)` + descartes visíveis na UI mesmo com planos gerados | 🟢 | 2026-10-01 |
| AP-014 | Planejamento (IS-043): piso da fila Disc.Tec. = última aula modular registrada no portal, antes do calendário/tolerância | 🟢 | 2026-10-01 |
| AP-015 | Planejamento (IS-044): slot fantasma 09:10 na grade gerava planos em horário inexistente no portal — limpeza nos 3 espelhos + renumeração 1..8 | 🟢 | 2026-10-02 |
| AP-016 | Planejamento (IS-045): fila dos planos passa a consultar o "livro-caixa" (`master_config`) em vez de ordenar por título — aulas especiais em zonas livres {01-08}{09-16}[LIVRE]{17-24}{25-32}[LIVRE] — fase 1 (fila + aba 8510) implementada e validada | 🟢 | 2026-10-02 |
| AP-017 | Planejamento (IS-046): piso da fila Disc.Tec. passa a valer o **dia** da última aula modular (transição no mesmo dia) em vez de +1 dia — slot 03/06 08:10 da I-A era descartado por `antes_inicio_disciplina` | 🟢 | 2026-10-02 |
| AP-018 | Planejamento (IS-047): grade horária com monitor dos 3 espelhos (SQLite/JSON/Supabase) + edição mover/adicionar/remover na ⚙️ Config — mudança Sex 11:30/13:30 → Qua (I-A) aplicada e planos renumerados | 🟢 | 2026-10-02 |

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

## AP-008 — Planejamento: aba Consolidadas + Gantt do fluxo letivo 🟢

**Pedido:** visão anual das turmas (carga × andamento por disciplina) em uma
aba própria, com filtro por turma; depois, expor o **fluxo letivo anual**
(janelas de `restricoes_planejamento`) para colocar cada disciplina em
perspectiva dentro do seu escopo.

**Solução:**
- Nova navegação **📈 Consolidadas** (`_SECOES` + `st.radio` logo após o
  Painel) com `secao_consolidadas()`.
- `consolidadas_data(turma_filtro)` (`@st.cache_data(ttl=30)`): por
  turma × disciplina — carga (`subjects.max_hours`), registradas
  (`historico_aulas`, excluindo `Aula Exclu%`), prontas/pendentes (`.txt` em
  `aulas/prontas|pendentes`), fila (`planejamento`) e
  `faltantes = max(0, carga − reg − prontas − pendentes)`.
- **Carga corrigida para 880h** (11 disciplinas × 40h × 2 turmas, base
  `data/Turmas/Escola.txt`): agrupa aliases pelo **nome canônico**
  (`_chave_disc()` — remove `(…)`, `2026A/B`, acento e caixa), porque
  `class_subjects` tem 14 linhas/turma com duplicatas de sync (POO = ids
  `4+30`; WEB FRONT-END = `6+31+33+34`, mas `turma_disciplina_config` só
  cobre `33/34 → 6`) → **1 linha de 40h por disciplina**. **"Caderno de
  Atividades"** (subject 35) fica fora da carga; `ativa = algum membro
  ativo`; a base **não** filtra inativas (todas as 22 linhas aparecem).
- UI: seletor "Todas as turmas" (default), 5 KPIs, `st.progress` de avanço,
  ⚠️ de excedente, gráfico 1 (fluxo empilhado por disciplina), gráfico 2
  (carga anual × registradas por turma) e tabela **Detalhamento**.
- **Gantt "Janela de cada disciplina no ano letivo"** (Altair, 22 barras):
  barra `inicio → fim` por disciplina, cor por escopo (Anual > 200 dias /
  Mensal), régua tracejada = hoje, ordenada por início; altura dinâmica
  `max(420, 26 × n + 90)` e `axis.labelLimit=260` (rotulos de 28 chars não
  truncam); coluna **Janela** na tabela.
- `load_janelas_disciplinas()`: lê `master_config['calendario_letivo.json']`
  (mesma fonte do gerador) com fallback p/ `data/calendario_letivo.json` e
  indexa `disciplina_id → {inicio, fim, carga}` pelos novos
  **`disciplina_ids`** de `restricoes_planejamento` (espelhados nas 2 fontes
  do SysAva; backup `escola_ativa_backup_calendario_20260929_200449.db`).
  **Datas corrigidas** por sync `data/calendario_letivo.json` →
  `master_config` (o master era import degradado de 14/06 sem
  `sabados_letivos`/`trimestres`; ver IS-038) → anuais `19/02–17/12`, igual
  ao fim do 3º trimestre.

**Arquivos:** `apps/planejamento_registro/planejamento_registro_streamlit.py`
(`consolidadas_data`, `load_janelas_disciplinas`, `secao_consolidadas`,
`_SECOES`), `apps/ISSUES.md`. Dados: `SysAva/data/calendario_letivo.json` +
`master_config['calendario_letivo.json']` (não versionados).

**Validação:** `py_compile` OK; QA navegador (8510, 0 erros de console):
Todas → **22 disc / carga 880 / 378 registradas / 25 prontas+pendentes /
478 faltantes / 43%**; filtro I-A → 11 / 440 / 204 / 2 / 235; Gantt com
**22 barras** (2 anuais + mensais restantes), alinhamento rótulo × barra
`delta = 0` nos 22 pares, eixo Y sem `2026A` nem sufixo de turma; coluna
Janela na tabela; sem "Caderno"; ⚠️ esperado de
`PROGRAMAÇÃO WEB FRONT-END (I-A)` (41 registros > 40 de carga).
Sync do calendário validado: 11/11 janelas idênticas nas 2 fontes,
`sabados_letivos` = 18 no `get_config`.

---

## AP-009 — Planejamento: exclusão em lote de planos na página Planos 🟢

**Pedido:** na página **Planos**, além da exclusão unitária, ter um seletor
em lote para excluir vários planos de uma vez (mesmo fluxo da seção
"Excluir planos de reposição do sábado", que já fazia multiselect).

**O que mudou:** novo expander **"🗑️ Excluir vários planos (seleção em
lote)"** logo abaixo do expander de exclusão unitária, dentro de
`secao_planos`:

- `st.multiselect` com as opções já filtradas da página (pasta
  `prontas/pendentes/registradas` × filtro turma/disciplina do sidebar),
  chave própria `planos_del_bulk_sel` (não reutiliza `zip_sel` para não
  misturar seleção de ZIP com exclusão);
- checkbox "Confirmo a exclusão dos planos selecionados"
  (`planos_del_bulk_conf`);
- botão `type="primary"` (`btn_del_planos_bulk`) desabilitado sem seleção
  + confirmação;
- loop sobre `excluir_plano(pasta, arq)` (remove o `.txt` e a linha do
  `planejamento` com os guards existentes), agregando contagem de arquivos,
  linhas de banco e erros; `_flash` com o resumo (warning se houve erro),
  `st.cache_data.clear()` e `st.rerun()` — idêntico ao padrão do Sábado e
  da exclusão unitária.

**Arquivos:** `apps/planejamento_registro/planejamento_registro_streamlit.py`
(`secao_planos`), `apps/ISSUES.md`.

**Validação:** `python -m py_compile` OK; QA navegador (8510, headless,
**0 erros de console**): Turma I-B → Disciplina IA → página Planos →
expanders unitário e em lote renderizados; multiselect listou os arquivos
da pasta, botão **desabilitado** sem seleção+confirmação. **E2E real:**
criado `plano_314114_11_2026-09-01_QA009.txt` (cópia com `AULA_NUM` vazio
p/ não tocar o banco) → selecionado no lote → confirmado → excluído com
flash **"1 arquivo(s) e 0 linha(s) do planejamento removidos."** → sumiu da
lista e do disco; arquivo original e a linha do `planejamento` intactos
(contagem 1 = pré-existente).

---

## AP-010 — Planejamento: editor do `master_config` + bloqueio de sábado letivo 🟢

**Pedido:** na página **Config**, poder **editar a tabela `master_config`**
(hoje só havia listagem somente-leitura + formulário de adição) e ter uma
opção para **bloquear os sábados letivos na geração automática de planos**
(o sábado passaria a ser somente manual, pela aba Sábados (reposição)).

**O que mudou:**

1. **Editor de parâmetros** (`secao_config`, § "Outros parâmetros"): o
   `st.dataframe` + `st.form` foram substituídos por `st.data_editor` com
   `num_rows="dynamic"` (adiciona/exclui linhas, célula de valor editável,
   colunas `chave`/`atualizado` de referência — renomear chave = excluir e
   recriar, avisado na caption). O botão **"💾 Salvar alterações"** só habilita
   com diff real; exclusões exigem checkbox de confirmação; o diff contra
   `listar_parametros()` normaliza o valor com `json.loads` (lista/número/
   booleano) ou guarda como texto, gravando sempre JSON válido via
   `set_config()`; `_flash` + `st.cache_data.clear()` + `st.rerun()`.
   Chaves `.json` (calendário/feriados) continuam fora da lista e protegidas.
2. **`core/banco.py::del_config(chave)`** (não existia): `DELETE` direto nos
   dois schemas (`key/value` e legado `chave/valor`), recusando chave vazia e
   chaves terminadas em `.json`.
3. **Bloqueio de sábado**: nova chave booleana `bloquear_sabados_letivos` na
   `master_config`, com seção própria na Config (mostra nº de sábados
   configurados + estado atual, checkbox + "💾 Salvar bloqueio de sábados").
   Em `core/gerador.py`, a montagem de `sabados_config` foi extraída para
   `resolver_sabados_config(calendario, project_root)` (com
   `flag_verdadeira()`/`sabados_bloqueados()`) — com a flag ativa retorna
   `{}`, e o gerador **pula qualquer sábado** (regra pré-existente: dia sem
   entrada em `sabados_config` é ignorado). `debug_info` ganhou
   `sabados_configurados`/`sabados_bloqueados`.
4. **Avisos de estado**: caption "🚫 Sábados bloqueados nesta geração" na
   seção de geração da aba Planos e `st.info` "🚫 Bloqueio ativo…" na aba
   Sábados (reposição). A geração **manual** de sábado
   (`gerar_plano_reposicao`/`gerar_reposicao_dia`) não passa por
   `sabados_config` e continua funcionando com a flag ligada; planos de
   sábado já existentes não são afetados.

**Arquivos:** `apps/planejamento_registro/planejamento_registro_streamlit.py`
(`secao_config`, `secao_planos`, `secao_sabados`, helper
`bloqueio_sabados_on()`), `apps/planejamento_registro/core/banco.py`,
`apps/planejamento_registro/core/gerador.py`, `apps/ISSUES.md`.

**Validação:** `python -m py_compile` OK; harness Python: flag ON →
`resolver_sabados_config()` vazio (18 sábados → 0), OFF → 18 entradas,
flag legada `"true"` reconhecida e revertida; roundtrip
`set/get/del_config` + recusa de `.json`/chave vazia; 4 chaves originais
intactas ao final. QA navegador (8510, headless, **0 erros de console**):
Config renderiza editor + seção de bloqueio (form antigo removido). **E2E
real:** botão "Add row" + duplo-clique nas células → criar `qa_ap010`
(**1 criado**) → editar para `valor2` (**1 alterado**, conferido no banco)
→ seleção de linha + Delete → checkbox de confirmação → salvar (**1
excluído**, removido do banco) → toggle do bloqueio **ON** → captions em
Config/Planos/Sábados confirmados → **OFF** → "Atual: liberado" (flag
final `false` no banco).

---

## AP-011 — Planejamento: geração de disciplinas modulares por janela do plano (±tolerância) 🟢

**Problema:** gerar planos de **Fundamentos de UI/UX (disc 8)** retornava 0
planos sem explicação. Causa raiz dupla:

1. Slots genéricos da grade ("Disc.Tec.") eram resolvidos pela disciplina
   mensal stale de `settings.disciplina_mensal_*` (escrita só pela página
   antiga da API) = FRONT-END — engessava **todos** os slots na mesma
   disciplina mesmo depois da janela dela encerrar; com o filtro
   disciplina=Fundamentos, nenhum slot passava.
2. Mesmo resolvendo certo, `cfg_alias` caía no fallback "primeira linha da
   turma" de `turma_disciplina_config` → Fundamentos herdava
   `aliases_id=6` do Front-End → seq inicial 17 (histórico do Front) →
   `max_hours`/faixa de aulas descartava tudo (e alias/conteúdo errados).

**Solução:**

- Resolução dos slots genéricos agora é **por data do plano anual**
  (`restricoes_planejamento`) com **tolerância de ±15 dias** por janela
  (parâmetro editável `tolerancia_janela_dias` na ⚙️ Config, padrão 15).
  Novos helpers `tolerancia_janela()`, `janelas_modulares()` e
  `janela_por_data()` em `core/gerador.py`: anuais (>300 dias) ficam de
  fora; disputa de janelas sobrepostas por menor distância à janela
  original (empate → mais antiga). Quando a disciplina **filtrada** tem
  janela, data dentro da janela tolerada resolve para **ela** (override
  sobre a janela vizinha). `settings.disciplina_mensal_*`,
  `get_next_modular_subject` e o fallback por turma saíram do caminho de
  geração (legado da era da API).
- `cfg_alias`: só linha exata `(turma, disciplina)` ou linha cujo
  `aliases_id` bate com a disciplina resolvida — nunca "primeira linha da
  turma".
- **Feedback de 0 planos**: `debug_counters` ganhou
  `resolvido_por_disciplina` e `descartados` (filtro/início/bloqueio/
  max_hours/faixa); a UI exibe aviso com o resumo e caption com a
  tolerância vigente; o `debug` inclui `tolerancia_janela_dias` e
  `janelas_plano`.

**Arquivos:** `apps/planejamento_registro/core/gerador.py`,
`apps/planejamento_registro/planejamento_registro_streamlit.py`,
`apps/ISSUES.md`.

**Validação:** `py_compile` OK; harness das janelas com o calendário real
(8 modulares, sem anuais; disputas: 25/05→Front-End, 10/06→Fundamentos,
04/07→Fundamentos, 05/07→Móveis, 30/09→Arquitetura, 15/01→fora). **E2E
navegador (8510, 0 erros de console):** Planos → I-B → Fundamentos →
intervalo 1–2 → Gerar → **2 planos reais** (`plano_314114_8_2026-05-21_
0910.txt` aula 1 e `..._2026-05-28_0910.txt` aula 2 — datas dentro da
janela tolerada 18/05–18/07, conteúdo/frequência corretos; linhas de
`planejamento` conferidas no banco). Antes da correção o mesmo fluxo
caía no novo aviso: "resolvido Fundamentos (57) | descartes: filtro
(177), max_hours (33), faixa (24)". Regressão sem escrita
(`aula_min=999`): I-A/Fundamentos e I-B/Front-End → `generated=0`, sem
exceções.

---

## AP-012 — Planejamento: reconciliação do `historico_aulas` com o portal iSeduc 🟢

**Problema:** a sincronização fechava com **Portal 418 × Local 601 e 189
órfãs** no `historico_aulas`. Causa raiz (188 linhas gravadas com o nome cru
da turma `EMTPDES-SIS-2ª SERIE - INTEGRAL-I-A/B`) e limpeza dos dados estão
documentadas em `SysAva/docs/ISSUES_LOCAIS.md` (**IS-041**).

**Neste repositório:**
1. **`rodar_raspagem(reconciliar=False)`** — passa `--reconciliar` para o
   `apps/api/tools/bot_raspagem.py` quando marcado.
2. **Checkbox "🧹 Reconciliar histórico ao sincronizar"** (página Registro,
   chave `chk_reconciliar`, **padrão desligado**): apaga do `historico_aulas`
   as linhas que o portal não mostra. Sem a marcação a raspagem roda em
   dry-run e **lista no log** o que sairia — nada é apagado sem confirmação.
3. **`aviso_reconciliacao_pendente()`** — lê `data/logs/raspagem_ultimo.json`
   e alerta na tela com contagem e motivos enquanto a reconciliação estiver
   pendente (`reconciliacao.removidos` sem `aplicado`).
4. **`RELATORIO_RASPAGEM`** = `data/logs/raspagem_ultimo.json`.

**Arquivos:** `apps/planejamento_registro/planejamento_registro_streamlit.py`,
`apps/ISSUES.md`.

**Validação:** `py_compile` OK; comparação 411 × 411 → 0 faltantes / 0 órfãs;
reconciliação em banco de teste remove **só** a sujeira injetada (rótulo
antigo + status excluído), **protege** o par inexistente no portal e não é
executada em dry-run; `save_history` ignora linha sem mapeamento de
`turma_id`/`disciplina_id` e grava a disciplina com o nome canônico.

---

## AP-013 — Planejamento: numeração estável + descartes visíveis na UI 🟢

**Problema:** a geração de 01/10 pulou **24/09** (P.C.II, turma I-B) e recriou
o **nº 30 duplicado** (17/09 × 01/10). Reconstrução das rodadas e correção de
dados em `SysAva/docs/ISSUES_LOCAIS.md` (**IS-042**). Dois defeitos neste
repositório:

1. **D2 — base instável:** a partida da numeração somava `COUNT(*)` de linhas
   `pendente`/`pronta`; exclusões e a mudança de status
   (`pendente` → `registrada`) alteravam a base entre rodadas — o nº 30
   duplicado nasceu de um `force_overwrite` que zera a base só no histórico
   enquanto o intervalo `De/Até` era digitado contra a numeração antiga.
   **Agora:** `MAX(CAST(numero_aula AS INTEGER))` por (turma, disciplina) em
   modo normal (`core/gerador.py`); `force_overwrite` mantém a semântica
   IS-019 (renumerar a partir do histórico).
2. **D3 — descartes invisíveis:** `descartados`/`slots_pulados` só apareciam
   quando **0** plano era gerado; com planos gerados a mensagem era só
   "✅ N plano(s)" e datas mortas por `aula_menor_que_min`/`sem_licao_prontas`
   sumiam sem explicação (foi o caso de 24/09). **Agora:** com
   `generated > 0`, exibe `st.info` com os descartes (exceto
   `filtro_disciplina`, esperado em toda geração) + expander com os slots
   pulados.

**Arquivos:** `apps/planejamento_registro/core/gerador.py`,
`apps/planejamento_registro/planejamento_registro_streamlit.py`,
`apps/ISSUES.md`.

**Validação:** `py_compile` OK nos dois arquivos; rerun não-force P.C.II com
intervalo 31-34 → `generated: 0` (datas já existem) sem efeitos colaterais,
exercitando a nova query; base PCII = `max(hist 25, max_numero 34)` → próxima
data nova = 35 (a fórmula antiga daria 33/34 colidindo com as existentes);
D3 conferido na revisão do bloco — validar visualmente no app 8510 gerando
qualquer disciplina (aparece "Descartes nesta geração: …").

---

## AP-014 — Planejamento: piso da fila Disc.Tec. pelo portal antes do calendário 🟢

**Problema:** a geração de **Fundamentos de UI/UX** (Disc.Tec., turma I-A)
criou planos a partir de **18/05/2026** enquanto o módulo anterior
**Front-End** estava registrado no portal até **03/06/2026** (detalhamento em
`SysAva/docs/ISSUES_LOCAIS.md` → **IS-043**). Causa: o piso "após a última
aula registrada" era **por turma/disciplina** — Fundamentos, sem histórico
próprio, caía na `data_corte` (01/04) — e a tolerância ±15 dias da janela
anual (`janela_filtro`, AP-011) liberava 18/05 em diante.

**Correção:**
1. `core/datas.py` → nova `ultima_aula_modular(ids)`: `(ids_expandidos,
   {turma: data})` da última aula registrada entre as disciplinas modulares
   (janelas ≤300 dias, expandidas por `discipline_aliases`).
2. `core/gerador.py` → no gate de data, slots genéricos ou disciplina
   modular usam `max(inicio_disciplina, última_modular + 1 dia)` — o
   critério do **portal precede o calendário e a tolerância** (slot
   ocupado via `historico_set` já era o 1º gate e permanece). O debug da
   8510 expõe `piso_modular_turmas`.

**Arquivos:** `apps/planejamento_registro/core/datas.py`,
`apps/planejamento_registro/core/gerador.py`, `apps/ISSUES.md`.

**Validação:** sandbox A/B com cópia do banco (linhas 309197/8 apagadas) —
controle (código anterior) regenerou 4 datas antes do piso com
`antes_inicio_disciplina: 0`; corrigido → `antes_inicio_disciplina: 4`,
primeira linha 05/06 e nenhum dado < 04/06 (unit: 309197 piso 04/06,
314114 piso 30/05); `py_compile` OK. **Dados:** as 6 linhas abaixo do piso
foram removidas e as demais renumeradas pelo gerador (309197/8 = 1..4,
314114/8 = 1..8, `.txt` regravados na posição nova; backup
`escola_ativa_backup_is043_20261001_225025.db` + `aulas/_backup_is043/`),
procedimento validado em sandbox antes de aplicado em produção.

---

## AP-015 - Planejamento (IS-044): slot fantasma 09:10 na grade gerava plano em horário inexistente 🟢

**Problema:** a geração de Fundamentos (disc 8) criou planos no horário
**09:10–10:10** (segunda I-A em 06-08, aula 5; quinta I-B em 06-11, aula 8),
que **não existe no portal** — lá é **09:30–10:30** e a I-A tem só duas
aulas Disc.Tec. nas segundas. A `weekly_schedule` carregava **os dois**
horários nos 3 espelhos (SQLite local lido pelo gerador, Supabase e
`grade_horaria.json`) e a dedup por `(turma, dia, time_slot)` mantém ambos,
porque são chaves distintas. Detalhamento e correção de dados em
`SysAva/docs/ISSUES_LOCAIS.md` → **IS-044**.

**Neste repositório:** nenhum código foi alterado — o problema era de dados:
slots 09:10 removidos nos 3 espelhos (incluindo `DELETE` no Supabase de
produção: ids 2578/2569), JSON realinhado ao portal (09:30, Sex 11:30,
10:30=I.A.), 2 linhas de `planejamento` (12399, 12394) apagadas, os 2
`.txt` movidos para `aulas/_backup_is044/` e a fila **renumerada 1..8 pelo
próprio gerador** (force + intervalo 1–8, validado em sandbox antes),
incluindo a aula 8 no slot correto (I-A **06-10 08:10**; I-B **06-11
09:30**).

**Arquivos:** dados (`SysAva/data/escola_ativa.db`,
`SysAva/data/repo/plugins/grade_horaria.json`, `SysAva/aulas/*`),
`apps/ISSUES.md`.

**Validação:** sandbox idêntico à produção antes do apply; pós-execução
"TODAS AS VERIFICACOES OK" (8+8 linhas exatas, 0 linhas 09:10 em
`planejamento`/grade/Supabase, arquivos conferidos AULA_NUM 1..8, JSON com
os dias editados carregando); backups `escola_ativa_backup_is044_*.db` +
`aulas/_backup_is044/`.

---

## AP-016 — Planejamento (IS-045): fila dos planos via "livro-caixa" (aulas especiais) 🟢

**Status: fase 1 CONCLUÍDA e validada em 02/10.** Design completo e decisões
documentados em `SysAva/docs/ISSUES_LOCAIS.md` → **IS-045**.

**O que foi alterado neste repo:**
* `planejamento_registro/core/gerador.py` — build de `filas_livro` a partir
  de `services.livro_caixa.carregar_todos()` (chave `subject_id`), consumo
  posicional da fila por `seq_num` (posição → conteúdo do bloco ou aula
  especial da zona; a especial vira pseudo-lesson, não conta como "sem
  lição"), fallback para a fila legada sem doc/fora da cobertura,
  `estrategia_plano` + objetivos/recursos/atividade do item especial e
  counter `especiais` no retorno. O caminho legado (`_ordenar_lessons_fila`
  + índice posicional) continua intacto para disciplinas sem livro-caixa.
* `planejamento_registro/planejamento_registro_streamlit.py` — seção "📚
  Livro-Caixa" no rádio de navegação: criar estrutura padrão/linear,
  recalcular+salvar resolução, métricas/conferência, tabela da fila
  resolvida, editor de zonas livres e remoção do livro-caixa.
* `apps/ISSUES.md` (este registro).

**Validação (02/10):** unitário do model' (`_lc_unit.py`, 25+ asserções) e
sandbox `_lc_sandbox.py` (cópia do DB em `%TEMP%\lc_sandbox`, disciplina 8 /
turma 309197): doc `blocos [[1,4],[5,6]]` + 2 zonas → 8 planos com
`AULA_NUM` 06/07 divergindo do título (Aula 5/Aula 6), 2 especiais nas
posições 5 e 8 com estratégias vindas do item, `sem_licao=0`; doc removido →
regressão legada idêntica (`especiais=0`). Smoke da UI no 8511 via
browser-automation: aba renderiza sem erros de console (leitura apenas).

**Observação:** reiniciar/recarregar o app 8510 para ver a nova aba.

**Pendências (fases 2/3):** Atividades (lançamento por tipo nas posições) e
abertura de zonas/especiais no gerador.

---

## AP-017 — Planejamento (IS-046): piso da fila Disc.Tec. vale o dia da última aula (transição no mesmo dia) 🟢

**Alteração:** em `planejamento_registro/core/gerador.py`, o piso
`max(inicio_disciplina, última_modular + 1 dia)` passou a ser
`max(inicio_disciplina, última_modular)`. No dia em que a disciplina
anterior termina, os slots livres restantes já podem ir para a seguinte —
o slot da aula registrada continua protegido pela ocupação, a própria
disciplina continua com `inicio_disciplina` (+1) e datas anteriores à
última aula seguem bloqueadas (IS-043).

**Impacto:** em I-A o slot `03/06 08:10` (único DT livre de junho) deixa de
ser descartado por `antes_inicio_disciplina`; a I-B e o feriado de
Corpus Christi (04/06) ficam inalterados.

**Validação:** sandbox `_trans_sandbox.py` — fase A: 0 linhas < 03/06,
exatamente 1 linha 03/06 08:10 nº 1, 40 aulas nums 1..40 monotônicos;
fase B: I-B começa 01/06 e 0 linhas em 04/06 (feriado) — ambas OK;
regressão `_lc_sandbox.py` (IS-045) OK; `py_compile` OK. Detalhes em
`SysAva/docs/ISSUES_LOCAIS.md` → **IS-046**.

**Produção (02/10):** Fundamentos I-A regenerada com **force + intervalo
1..31** (backup `escola_ativa_backup_is046_20261002_153325.db`, `.txt`
antigos em `aulas/_backup_is046/`): 31 linhas 1..31 de 03/06 08:10 a
06/30 07:10, 31 arquivos consistentes em `aulas/prontas/`.

**Arquivos:** `planejamento_registro/core/gerador.py`.

---

## AP-018 — Planejamento (IS-047): grade horária com monitor dos 3 espelhos + edição na ⚙️ Config 🟢

**O que foi alterado neste repo:**
* `planejamento_registro/core/grade.py` (novo) — leitura/edição dos 3
  espelhos da grade horária (SQLite `weekly_schedule`, `grade_horaria.json`,
  Supabase): `carregar_sqlite/carregar_json/carregar_supabase`,
  `divergencias()` (status slot a slot), `impacto()` (registradas + planos
  com aviso "fora da grade") e `mover/adicionar/remover` — cada edição
  grava nos 3 espelhos (dedup no SQLite, JSON reescrito, delete+upsert na
  nuvem).
* `planejamento_registro/planejamento_registro_streamlit.py` — seção "🗓️
  Grade horária (monitor + edição)" na ⚙️ Config, com abas 📋 Grade /
  🔀 Espelhos / ⚖️ Impacto / ✏️ Editar e confirmação antes de gravar.

**Dados (02/10):** mudança real **Sex 11:30/13:30 → Qua 11:30/13:30** (I-A,
Disc.Tec.) aplicada nos 3 espelhos; planos disc 8 regenerados (force 1..31,
8 planos movidos para quarta); backups em
`escola_ativa_backup_is047_20261002_171734.db` e `aulas/_backup_is047/`.

**Validação:** sandbox `_grade_sandbox.py` (mover/dedup/round-trip/guards
OK), produção `_grade_apply.py` (3 espelhos idênticos, 0 divergências, 8
planos em quarta / 0 em sexta) e smoke da UI 8511 via browser-automation (4
abas + editor, "Espelhos consistentes", 0 erros de console). Detalhes em
`SysAva/docs/ISSUES_LOCAIS.md` → **IS-047**.

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
