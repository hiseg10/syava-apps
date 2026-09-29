import sys
import os
import streamlit as st
import pandas as pd
import glob
import json
from datetime import datetime

# Encontrar a raiz do projeto (SysAva) para poder importar o services
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from dotenv import load_dotenv
    import services.database as db
    from services.database import supabase
except ImportError as e:
    st.error(f"Erro de importação: {e}")
    st.stop()

# Configuração da página
st.set_page_config(
    page_title="Monitor de Consumo Supabase",
    page_icon="⚡",
    layout="wide"
)

# Garantir que o diretório de logs existe
logs_dir = os.path.join(project_root, "data", "logs")
os.makedirs(logs_dir, exist_ok=True)
db_history_file = os.path.join(logs_dir, "supabase_db_size_history.json")

st.title("📊 Monitor de Consumo e Tráfego do Supabase")
st.markdown("""
Este painel ajuda você a entender o porquê de o projeto ter ultrapassado o limite de **5GB de saída de banda (Egress)** do plano gratuito do Supabase e ensina como mitigar isso em poucos minutos usando **boas práticas de Streamlit e consultas parciais**.

### ⚠️ Por que a banda estoura tão rápido com o Streamlit?
O Streamlit tem uma arquitetura **"Rerun"**: cada clique em um botão, mudança de filtro ou interação do usuário recarrega o script inteiro. 
* Se você buscar tabelas cheias do banco sem cache (`@st.cache_data`) ou usando `select("*")` (trazendo descrições longas e conteúdos inteiros), cada clique do usuário baixa vários megabytes de novo!
* 1 aluno gerando 10MB de tráfego em cliques por dia = 300MB/mês. 
* **50 alunos ativos** gerando isso = **15GB de tráfego/mês** (estourando os 5GB gratuito facilmente).
""")

# Abas
tab_live, tab_audit, tab_sim, tab_guide = st.tabs([
    "📊 Diagnóstico em Tempo Real",
    "🕵️ Auditor de Código Automático",
    "💸 Simulador de Tráfego",
    "🛠️ Guia Prático de Mitigação"
])

# --- TAB 1: DIAGNÓSTICO EM TEMPO REAL ---
with tab_live:
    st.header("🛸 Estatísticas Atuais das Tabelas no Supabase")
    
    # Função para obter dados de consumo
    @st.cache_data(ttl=60)
    def fetch_db_stats():
        tables = {
            'lessons': {'name': 'Aulas', 'desc': 'Conteúdo pedagógico e descrições das aulas'},
            'forum_posts': {'name': 'Mensagens do Fórum', 'desc': 'Perguntas e respostas de alunos no fórum'},
            'historico_aulas': {'name': 'Histórico de Aulas (Robô)', 'desc': 'Registros sincronizados automaticamente'},
            'student_assessments': {'name': 'Submissões de Avaliações', 'desc': 'Resultados e notas de provas de alunos'},
            'app_users': {'name': 'Usuários do App', 'desc': 'Contas de alunos, professores e administradores'},
            'assessments': {'name': 'Avaliações', 'desc': 'Provas e testes cadastrados'},
            'classes': {'name': 'Turmas', 'desc': 'Turmas cadastradas'},
            'subjects': {'name': 'Disciplinas', 'desc': 'Matérias pedagógicas da grade'}
        }
        
        stats = []
        for t, meta in tables.items():
            try:
                # Contagem de linhas
                res = supabase.table(t).select("*", count='exact').limit(1).execute()
                count = res.count or 0
                
                # Tamanho estimado
                avg_size_bytes = 0
                if t == 'lessons':
                    sample = supabase.table(t).select("full_content, description").execute()
                    sizes = [len(r.get('full_content') or '') + len(r.get('description') or '') for r in sample.data]
                    avg_size_bytes = sum(sizes) / len(sizes) if sizes else 1000
                elif t == 'forum_posts':
                    sample = supabase.table(t).select("message").execute()
                    sizes = [len(r.get('message') or '') for r in sample.data]
                    avg_size_bytes = sum(sizes) / len(sizes) if sizes else 150
                elif t == 'historico_aulas':
                    avg_size_bytes = 150
                elif t == 'student_assessments':
                    avg_size_bytes = 120
                else:
                    avg_size_bytes = 100
                
                total_weight_kb = (count * avg_size_bytes) / 1024
                
                stats.append({
                    "Tabela real": t,
                    "Nome Amigável": meta['name'],
                    "Descrição": meta['desc'],
                    "Qtd de Linhas": count,
                    "Tam. Médio Registro": f"{avg_size_bytes:.1f} bytes",
                    "Peso Total Estimado (KB)": f"{total_weight_kb:.2f} KB",
                    "raw_weight_kb": total_weight_kb,
                    "Nível de Risco de Egress": "🔴 Alto (Texto Longo)" if t in ['lessons', 'forum_posts'] and count > 100 else ("🟡 Médio" if count > 1000 else "🟢 Baixo")
                })
            except Exception as e:
                stats.append({
                    "Tabela real": t,
                    "Nome Amigável": meta['name'],
                    "Descrição": meta['desc'],
                    "Qtd de Linhas": "Erro ao ler",
                    "Tam. Médio Registro": "-",
                    "Peso Total Estimado (KB)": "-",
                    "raw_weight_kb": 0,
                    "Nível de Risco de Egress": "⚪ Desconhecido"
                })
        return stats

    stats_list = fetch_db_stats()
    df_stats = pd.DataFrame(stats_list)
    
    # Mostrar peso total
    total_db_kb = df_stats["raw_weight_kb"].sum()
    total_db_mb = total_db_kb / 1024
    
    # --- LOG DE EVOLUÇÃO DE TAMANHO ---
    # Salva o tamanho atual em um histórico de logs local
    if total_db_kb > 0:
        current_time = datetime.now().isoformat()
        db_history = []
        if os.path.exists(db_history_file):
            try:
                with open(db_history_file, "r", encoding="utf-8") as hf:
                    db_history = json.load(hf)
            except Exception:
                pass
        
        # Só adiciona uma nova entrada se a última foi há mais de 10 segundos, para evitar spam
        should_add = True
        if db_history:
            last_entry = db_history[-1]
            try:
                last_time = datetime.fromisoformat(last_entry['timestamp'])
                if (datetime.now() - last_time).total_seconds() < 10:
                    should_add = False
            except Exception:
                pass
                
        if should_add:
            db_history.append({
                "timestamp": current_time,
                "db_size_mb": round(total_db_mb, 4)
            })
            # Mantém apenas os últimos 50 registros para não crescer infinitamente
            if len(db_history) > 50:
                db_history = db_history[-50:]
            with open(db_history_file, "w", encoding="utf-8") as hf:
                json.dump(db_history, hf, indent=4)

    # Renderização da tela
    col_m1, col_m2 = st.columns([2, 1])
    with col_m1:
        st.metric("📦 Peso de Dados Textuais do Banco (Estimado)", f"{total_db_mb:.2f} MB")
    with col_m2:
        # Botão para baixar o relatório em CSV
        csv_report = df_stats[["Nome Amigável", "Tabela real", "Qtd de Linhas", "Tam. Médio Registro", "Peso Total Estimado (KB)", "Nível de Risco de Egress"]].to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 Baixar Relatório de Consumo (CSV)",
            data=csv_report,
            file_name=f"relatorio_consumo_supabase_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

    # Exibição da tabela principal
    st.dataframe(
        df_stats[["Nome Amigável", "Tabela real", "Qtd de Linhas", "Tam. Médio Registro", "Peso Total Estimado (KB)", "Nível de Risco de Egress"]],
        use_container_width=True,
        hide_index=True
    )

    # --- SEÇÃO DE GRÁFICO DE EVOLUÇÃO ---
    st.write("### 📈 Histórico de Tamanho do Banco de Dados")
    if os.path.exists(db_history_file):
        try:
            with open(db_history_file, "r", encoding="utf-8") as hf:
                db_hist_data = json.load(hf)
            
            if len(db_hist_data) >= 2:
                plot_data = []
                for entry in db_hist_data:
                    dt = datetime.fromisoformat(entry['timestamp']).strftime("%d/%m %H:%M:%S")
                    plot_data.append({
                        "Data/Hora": dt,
                        "Tamanho do Banco (MB)": entry['db_size_mb']
                    })
                df_plot = pd.DataFrame(plot_data)
                st.line_chart(df_plot.set_index("Data/Hora"), y="Tamanho do Banco (MB)")
            else:
                st.info("💡 **Aviso:** O gráfico de evolução de tamanho aparecerá assim que você rodar diagnósticos em momentos diferentes (dados históricos sendo acumulados).")
        except Exception as e:
            st.error(f"Erro ao renderizar gráfico de histórico: {e}")
    
    st.info("""
    💡 **Análise de Diagnóstico:** Embora o banco de dados inteiro pese apenas alguns megabytes (~3 MB), o problema da banda de saída **não é o tamanho do banco**, mas sim a **quantidade de vezes que ele é baixado inteiramente**!
    Se 100 alunos navegarem no aplicativo e cada ação deles recarregar todos os registros de `lessons` e `forum_posts`, você transfere 3MB em cada clique. 
    * 100 alunos * 20 cliques/dia * 3MB = **6GB de saída em apenas 1 DIA!**
    """)

    # Botão para atualizar dados manualmente
    if st.button("🔄 Atualizar Diagnóstico do Banco"):
        st.cache_data.clear()
        st.rerun()

# --- TAB 2: AUDITOR DE CÓDIGO AUTOMÁTICO ---
with tab_audit:
    st.header("🕵️ Auditor Automático de Consultas no Código")
    st.markdown("""
    Este scanner varre o arquivo `services/database.py` do projeto em busca de padrões de consulta ineficientes que trazem dados demais para o Streamlit.
    """)
    
    db_file_path = os.path.join(project_root, "services", "database.py")
    
    if not os.path.exists(db_file_path):
        st.error(f"Arquivo `services/database.py` não encontrado no caminho: {db_file_path}")
    else:
        with open(db_file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        heavy_select_star = []
        for idx, line in enumerate(lines):
            if '.select("*")' in line or ".select('*')" in line:
                context = "".join(lines[max(0, idx-2):idx+1])
                for table in ['lessons', 'forum_posts', 'student_assessments', 'user_history']:
                    if f'table("{table}")' in context or f"table('{table}')" in context:
                        heavy_select_star.append({
                            "Linha": idx + 1,
                            "Tabela": table,
                            "Código Encontrado": line.strip(),
                            "Contexto": context.strip()
                        })
                        
        if len(heavy_select_star) == 0:
            st.success("🎉 **Nenhum padrão crítico de `select('*')` em tabelas pesadas foi detectado nas consultas diretas!**")
        else:
            st.warning(f"⚠️ **Detectadas {len(heavy_select_star)} consultas ineficientes do tipo `select('*')` em tabelas volumosas!**")
            st.markdown("Cada uma destas consultas baixa todos os campos (incluindo conteúdos de texto maciços) desnecessariamente, gerando alto tráfego:")
            
            for item in heavy_select_star:
                with st.expander(f"Linha {item['Linha']}: Consulta em `{item['Tabela']}`"):
                    st.code(item['Código Encontrado'], language="python")
                    st.markdown(f"**Impacto:** Sempre que esta consulta roda, ela baixa todo o conteúdo de `{item['Tabela']}` (como as descrições e textos longos).")
                    st.markdown("**Como corrigir:** Substitua o `*` apenas pelas colunas estritamente necessárias para a listagem inicial. Exemplo:")
                    if item['Tabela'] == 'lessons':
                        st.code('supabase.table("lessons").select("id, title, description, week, subject_id")', language="python")
                    elif item['Tabela'] == 'forum_posts':
                        st.code('supabase.table("forum_posts").select("id, user_name, created_at, lesson_id")', language="python")

# --- TAB 3: SIMULADOR DE TRÁFEGO ---
with tab_sim:
    st.header("💸 Simulador de Banda de Saída")
    st.markdown("Ajuste os parâmetros abaixo para entender como as interações dos alunos se multiplicam em tráfego no Supabase.")
    
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        sim_students = st.slider("👥 Alunos ativos por dia", min_value=1, max_value=200, value=30, step=5)
        sim_clicks = st.slider("🖱️ Cliques/Interações por aluno ao dia", min_value=5, max_value=100, value=20, step=5)
        
    with col_s2:
        sim_cache = st.toggle("⚡ Ativar cache de dados (`@st.cache_data`)", value=False)
        sim_partial_select = st.toggle("🔍 Usar consultas parciais (Evitar `select('*')`)", value=False)

    # Cálculo da simulação
    base_page_size_kb = total_db_kb if total_db_kb > 0 else 2500
    
    if sim_partial_select:
        click_payload_kb = base_page_size_kb * 0.15 
    else:
        click_payload_kb = base_page_size_kb
        
    if sim_cache:
        click_payload_kb = click_payload_kb * 0.10

    daily_traffic_mb = (sim_students * sim_clicks * click_payload_kb) / 1024
    monthly_traffic_gb = (daily_traffic_mb * 30) / 1024
    
    # Interface de Resultados
    st.write("---")
    st.write("### 📈 Estimativa de Consumo Mensal")
    
    c_m1, c_m2, c_m3 = st.columns(3)
    with c_m1:
        st.metric("Consumo Diário Estimado", f"{daily_traffic_mb:.2f} MB")
    with c_m2:
        if monthly_traffic_gb > 5.0:
            st.metric("Consumo Mensal Estimado", f"🔴 {monthly_traffic_gb:.2f} GB", delta=f"{monthly_traffic_gb - 5.0:.2f} GB Acima do Limite", delta_color="inverse")
        else:
            st.metric("Consumo Mensal Estimado", f"🟢 {monthly_traffic_gb:.2f} GB", delta=f"{5.0 - monthly_traffic_gb:.2f} GB Abaixo da Cota")
    with c_m3:
        st.metric("Porcentagem da Cota de 5GB Usada", f"{(monthly_traffic_gb / 5.0) * 100:.1f}%")

    if monthly_traffic_gb > 5.0:
        st.error(f"🚨 **ALERTA:** Com as configurações atuais você ultrapassará os **5GB grátis** do Supabase! (Consumo estimado: {monthly_traffic_gb:.2f} GB/mês)")
        st.markdown("**👉 Experimente ligar o Cache e as Consultas Parciais nos botões acima para ver o consumo despencar instantaneamente!**")
    else:
        st.success(f"🎉 **EXCELENTE:** Com a otimização ativa, seu consumo ficará em apenas **{monthly_traffic_gb:.2f} GB/mês**, operando folgadamente dentro da cota gratuita de 5GB!")

# --- TAB 4: GUIA PRÁTICO DE MITIGAÇÃO ---
with tab_guide:
    st.header("🛠️ Como Resolver o Problema em 3 Passos Simples")
    
    st.markdown("""
    Siga estes 3 passos para reduzir seu tráfego em **até 90%** e nunca mais se preocupar em pagar taxas extras do Supabase!
    """)
    
    # Passo 1
    st.write("### 1️⃣ Adicione Caching no Streamlit (O mais importante!)")
    st.markdown("""
    O cache faz com que o Streamlit salve o resultado das consultas na memória do servidor. Se outro aluno entrar ou o mesmo aluno clicar em um botão, o Streamlit entrega o resultado instantaneamente, **sem fazer nenhuma chamada ou gastar banda com o Supabase**!
    
    **Como fazer no arquivo `services/database.py`:**
    """)
    st.code("""
import streamlit as st

@st.cache_data(ttl=300) # Salva em cache por 5 minutos (300 segundos)
def get_lessons():
    # Sua consulta ao Supabase aqui...
    res = safe_execute(lambda sb: sb.table("lessons").select("*").order("id").execute())
    return res.data if res else []
    """, language="python")
    
    # Passo 2
    st.write("### 2️⃣ Pare de usar `select('*')` para listagens!")
    st.markdown("""
    Quando os alunos entram no app, eles veem uma **lista de aulas** (apenas título, semana, disciplina). Não há necessidade de baixar o conteúdo completo da aula (`full_content`) nesse momento! Baixe o conteúdo apenas quando o aluno clicar na aula correspondente.
    
    **Exemplo de Otimização:**
    """)
    st.code("""
# ❌ ANTES (Consome muita banda):
def get_lessons_for_subject(subject_id):
    res = supabase.table("lessons").select("*").eq("subject_id", subject_id).execute()

#  DEPOIS (Super otimizado, consome 95% menos banda!):
def get_lessons_list_for_subject(subject_id):
    # Seleciona apenas os metadados leves!
    res = supabase.table("lessons").select("id, title, week, subject_id").eq("subject_id", subject_id).execute()
    
# Crie uma função separada para carregar o conteúdo apenas quando o aluno abrir a aula:
def get_lesson_content(lesson_id):
    res = supabase.table("lessons").select("id, full_content").eq("id", lesson_id).execute()
    """, language="python")

    # Passo 3
    st.write("### 3️⃣ Crie Paginação no Fórum")
    st.markdown("""
    O fórum tem **3.309 posts**. Se toda vez que o aluno entrar no fórum você buscar todos os 3.309 posts com `.select("*")`, você baixará cerca de 500KB de texto redundante.
    
    **Como fazer no arquivo `services/database.py`:**
    """)
    st.code("""
# Adicione limites e paginação nas consultas do fórum:
def get_latest_forum_posts(limit: int = 50):
    response = supabase.table("forum_posts")\\
        .select("*")\\
        .order("created_at", desc=True)\\
        .limit(limit)\\
        .execute()
    return response.data
    """, language="python")

# Barra lateral informativa
st.sidebar.title("🔌 Status da Conexão")
if db.is_db_connected():
    st.sidebar.success("Supabase Conectado!")
else:
    st.sidebar.error("Supabase Desconectado!")

st.sidebar.markdown("---")
st.sidebar.info("""
**Dica de Ouro:**
O cache de 5 minutos (`ttl=300`) nas funções de leitura de aulas e fórum é o maior herói de economia de cota em produção!
""")
