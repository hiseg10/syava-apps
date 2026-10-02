# CI — GitHub Actions (syava-apps)

Workflow em `.github/workflows/ci.yml` — fase inicial: **sintaxe de todo o
código do repo em cada push/PR**, com o passo de testes pronto para ligar sozinho
quando surgir a pasta `tests/`. Versão leve do CI que o SysAva (repo irmão)
também recebeu; ver `SysAva/docs/CI_WORKFLOW.md`.

## Gatilhos

* `push` em qualquer branch
* `pull_request`

## O que roda (job `testes`, ubuntu-latest, Python 3.11)

| Passo | O quê | Falha quando... |
|---|---|---|
| **Sintaxe** | `git ls-files -z "*.py" \| xargs -0 -r python -m py_compile` — compila **só os `.py` versionados** (17 na data da escrita: `planejamento_registro/**` etc.) | qualquer arquivo Python rastreado tiver erro de sintaxe |
| **Testes (pytest)** | `pip install -r requirements.txt pytest` + `pytest -q` | **só aparece quando existir `tests/**/*.py`** (`if: hashFiles(...)`) — hoje oculto por design |

## Rodar o mesmo em casa

```bash
git ls-files -z "*.py" | xargs -0 -r python -m py_compile   # sintaxe
pytest -q                                                   # quando existir tests/
```

## Como ampliar

1. Criar `tests/` na **raiz deste repo** (ex.: `tests/test_grade.py`) → o passo
   de pytest ativa sem tocar no YAML.
2. Candidatos naturais a cobertura (lógica pura, sem Streamlit):
   * `core/grade.py` — leitura/divergência/impacto/edição da grade (já tem
     sandbox de validação que virou teste fácil);
   * `core/datas.py` — feriados, `ultima_aula_modular`;
   * `core/gerador.py` — piso da fila Disc.Tec. (IS-043/046) e parser de quizzes.
3. Testes de UI do 8510 (AppTest) ficam numa fase seguinte.

---

Vinculado a: `ISSUES.md` (sem ID próprio — spike de infra CI).
