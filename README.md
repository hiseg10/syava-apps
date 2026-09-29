# syava-apps

Aplicações auxiliares do **SysAva** (utilitários Streamlit). Repositório
**aninhado** dentro de `SysAva/apps/`, ou seja, precisa viver dentro de um
checkout do SysAva para funcionar.

Repositório: <https://github.com/hiseg10/syava-apps>

## Requisitos

- Checkout do **SysAva** (`https://github.com/helioprofcaic/SysAva`) com este
  repositório dentro da pasta `apps/`.
- Python 3.11 e o ambiente virtual `.sysenv` do SysAva (o `run.bat` da raiz
  cria/gerencia ele).
- Dependências: `apps/requirements.txt` (subconjunto do `requirements.txt` do
  SysAva; na dúvida, use o do SysAva).

Os apps importam `services.*` e `apps/api/tools/*` da raiz do SysAva — por isso
**não rodam sozinhos** fora desse contexto.

## Como iniciar

Pelo menu do SysAva (raiz): `run.bat`

Ou pelo bootloader deste repositório, que detecta/cria o venv:

```bat
apps\run_apps.bat
```

## Aplicativos

| App | Porta | Descrição |
|---|---|---|
| `duplicate_checker/` | 8502 | Audita e limpa registros duplicados em `historico_aulas` |
| `supabase_monitor/` | 8503 | Diagnóstico de tamanho de tabelas, auditoria e egress do Supabase |
| `planejamento_registro/` | 8510 | Acompanhamento de planejamento e registro de aulas |
| `down_seductec/` | 8504 | Baixa PDFs e links de vídeo do portal SeducTec para `data/repo/<turma>/<disciplina>/S0X/seductec/` |
| `analise_notas/` | — | Scripts/notebook de análise de notas (gera dashboard HTML local) |

## Estrutura fora do escopo (não versionado)

`apps/api/` (API FastAPI + plugins), `apps/apis_gemini_key/`, `apps/data/`
(logs) e todos os dados gerados (backups `.db`, `.csv`, `html/`, PDFs) ficam
**fora** deste repositório — ver `.gitignore`.

> ⚠️ Repo público: nunca commite chaves, `secrets.toml`, backups de banco ou
> dados de alunos (notas, frequência, nomes).

## Issues

Problemas e melhorias deste repositório são registrados em
[`ISSUES.md`](ISSUES.md) com IDs `AP-NNN`.
