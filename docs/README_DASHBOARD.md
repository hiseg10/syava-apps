# 📊 Dashboard Dinâmico de Análise de Notas

Versão 100% client-side do notebook `analise_notas.ipynb`. Os HTMLs antigos
(`analise_completa.html`, `grafico_*.html`, `tabela_*.html`) eram **estáticos** —
gerados uma vez com os dados embutidos. Este novo dashboard busca os dados em
tempo real (do JSON local ou do Supabase) e renderiza tudo no navegador.

## 📂 Arquivos criados

| Arquivo | Função |
|---|---|
| `html/dashboard_dinamico.html` | Template visual com 4 abas + filtros |
| `html/dashboard.js`            | Lógica de carga, cálculo e renderização |
| `export_student_scores.py`     | Helper Python para exportar Supabase → JSON |

## 🚀 Como usar

### 1) Servir os arquivos (necessário por causa de `fetch` + CORS)

O `fetch()` do navegador exige HTTP. Abra um terminal na raiz do projeto:

```bat
cd apps\analise_notas\html
python -m http.server 8765
```

Depois acesse: **http://localhost:8765/dashboard_dinamico.html**

> ⚠️ Abrir o HTML via `file://` não funciona — o navegador bloqueia `fetch`
> de arquivos locais. Use sempre um servidor HTTP local.

### 2) Fonte de dados

No topo do dashboard há um seletor **"Fonte"**:

- **📁 Arquivo local** — busca `../../data/repo/plugins/student_scores.json`
- **☁️ Supabase** — chama a REST API direto do navegador

Para ativar o Supabase, edite `dashboard.js` e preencha:

```js
const CONFIG = {
    supabaseUrl:  'https://SEU-PROJETO.supabase.co',
    supabaseKey:  'SUA-ANON-PUBLIC-KEY',
    supabaseTable: 'student_scores',
};
```

> 🔐 **Segurança:** use a chave **anon/public** do Supabase (não a service_role).
> Se precisar de RLS mais restritivo, crie uma **view** específica para o dashboard.

### 3) Exportar dados do Supabase → JSON (opcional)

Se preferir trabalhar offline com o JSON local:

```bash
python apps/analise_notas/export_student_scores.py
```

Isso gera `data/repo/plugins/student_scores.json` respeitando:
- ✅ `select` explícito (sem `*`)
- ✅ pronto para cache com `@st.cache_data(ttl=300)` se integrado ao Streamlit

## 🎯 Funcionalidades

- **4 abas**: Médias por Disciplina · Pontos Qualitativos · Desempenho por Aluno · Tabela Completa
- **Filtro de aluno** (atualiza o gráfico 3 em tempo real)
- **Estatísticas gerais** (totais + médias T1/T2/T3)
- **Gráficos Plotly interativos** (zoom, hover, export PNG)
- **Responsivo** (testado em desktop e mobile)
- **Botão "Recarregar Dados"** para forçar refresh
- **Print-friendly** (`@media print` esconde controles)

## 🔄 Diferença para o notebook

| Notebook (estático) | Dashboard (dinâmico) |
|---|---|
| Precisa rodar Python para gerar HTML | Abre direto no navegador |
| Dados ficam congelados no HTML | Sempre lê a fonte mais recente |
| 1 aluno por vez (hardcoded) | Filtro dropdown com todos os alunos |
| 1 export = 1 arquivo | 1 HTML serve para todos os dados |