import sys
import os
import streamlit as st
import pandas as pd
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

# Configuração da Página
st.set_page_config(
    page_title="Verificador de Duplicatas",
    page_icon="🔍",
    layout="wide"
)

# Garantir que o diretório de logs existe
logs_dir = os.path.join(project_root, "data", "logs")
os.makedirs(logs_dir, exist_ok=True)
cleanup_history_file = os.path.join(logs_dir, "duplicate_cleanup_history.json")

st.title("🔍 Verificador de Duplicatas Inteligente")
st.markdown("""
Esta ferramenta foi desenvolvida para ajudar você a identificar e limpar de forma **100% segura** os registros duplicados na tabela `historico_aulas`.

### 🛡️ Por que esta ferramenta é segura?
1. **Lógica de Duplicidade Real:** O sistema considera duplicatas apenas se os registros compartilharem a **mesma Data**, o **mesmo Horário**, a **mesma Turma** e a **mesma Disciplina**.
2. **Preservação de Aulas Seguidas:** Se uma disciplina (como POO) tiver 3 aulas seguidas no mesmo dia, elas ocorrerão em **horários diferentes** (ex: *07:30 às 08:30*, *08:30 às 09:30*, etc.). Elas **NÃO** serão identificadas como duplicatas!
3. **Sempre mantemos um registro:** Para cada conjunto de duplicatas idênticas encontradas, o sistema mantém um registro ativo e apenas apaga as cópias extras redundantes.
""")

# Obter turmas e disciplinas para os filtros da barra lateral
@st.cache_data(ttl=60)
def get_filter_options():
    try:
        classes = db.get_classes()
        subjects = db.get_subjects()
        return classes, subjects
    except Exception as e:
        st.error(f"Erro ao obter dados de turmas/disciplinas: {e}")
        return [], []

classes, subjects = get_filter_options()

# Mapeamentos para exibição amigável
class_options = {c['id']: c['name'] for c in classes}
subject_options = {s['id']: s['name'] for s in subjects}

# Barra Lateral
st.sidebar.header("⚙️ Filtros de Segurança")

# Filtro de Turma
selected_class_name = st.sidebar.selectbox(
    "🏫 Filtrar por Turma",
    options=["Todas as Turmas"] + list(class_options.values())
)
selected_class_id = None
if selected_class_name != "Todas as Turmas":
    selected_class_id = [k for k, v in class_options.items() if v == selected_class_name][0]

# Filtro de Disciplina
selected_subject_name = st.sidebar.selectbox(
    "📚 Filtrar por Disciplina",
    options=["Todas as Disciplinas"] + list(subject_options.values())
)
selected_subject_id = None
if selected_subject_name != "Todas as Disciplinas":
    selected_subject_id = [k for k, v in subject_options.items() if v == selected_subject_name][0]

st.sidebar.markdown("---")
st.sidebar.header("🔧 Estratégia de Resolução")
strategy = st.sidebar.radio(
    "Qual registro manter de cada grupo?",
    options=["Manter o registro mais antigo (Recomendado)", "Manter o registro mais recente"],
    index=0
)

only_marked_dup = st.sidebar.checkbox(
    "Exibir apenas marcados como duplicados (`is_duplicate = True`)",
    value=False
)

# Buscar registros do banco
@st.cache_data(show_spinner="Buscando registros no Supabase...")
def fetch_historico_aulas():
    try:
        res = supabase.table("historico_aulas").select("*").execute()
        return res.data
    except Exception as e:
        st.error(f"Erro ao conectar ao banco de dados: {e}")
        return []

# Botão para limpar cache e recarregar dados
if st.sidebar.button("🔄 Recarregar Dados do Banco"):
    st.cache_data.clear()
    st.rerun()

all_records = fetch_historico_aulas()

if not all_records:
    st.info("Nenhum registro encontrado no histórico de aulas.")
else:
    # 1. Aplicar filtros em Python para máxima robustez
    filtered_records = []
    for r in all_records:
        if selected_class_id is not None:
            if r.get('turma_id') != selected_class_id and r.get('turma') != selected_class_name:
                continue
        if selected_subject_id is not None:
            if r.get('disciplina_id') != selected_subject_id and r.get('disciplina') != selected_subject_name:
                continue
        if only_marked_dup and not r.get('is_duplicate'):
            continue
            
        filtered_records.append(r)

    st.write(f"### 📊 Registros Analisados: {len(filtered_records)} de {len(all_records)} totais")

    # 2. Agrupar por chave única real (data_aula, horario, turma_id/turma, disciplina_id/disciplina)
    grouped = {}
    for r in filtered_records:
        t_key = r.get('turma_id') or r.get('turma') or 'Desconhecido'
        d_key = r.get('disciplina_id') or r.get('disciplina') or 'Desconhecido'
        key = (
            r.get('data_aula') or '',
            r.get('horario') or '',
            t_key,
            d_key
        )
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(r)

    # 3. Separar em grupos duplicados e registros a apagar/manter
    duplicate_groups = {}
    records_to_keep = []
    records_to_delete = []

    for key, rows in grouped.items():
        if len(rows) > 1:
            sorted_rows = sorted(rows, key=lambda x: x.get('id', 0))
            if strategy == "Manter o registro mais antigo (Recomendado)":
                keep_row = sorted_rows[0]
                delete_rows = sorted_rows[1:]
            else:
                keep_row = sorted_rows[-1]
                delete_rows = sorted_rows[:-1]
                
            duplicate_groups[key] = {
                'keep': keep_row,
                'delete': delete_rows,
                'all': sorted_rows
            }
            records_to_keep.append(keep_row)
            records_to_delete.extend(delete_rows)

    # Exibir resumo
    num_dups = len(records_to_delete)
    if num_dups == 0:
        st.success("🎉 **Nenhuma duplicata encontrada com os filtros atuais!** Todas as aulas têm chaves de horário, turma e disciplina únicas.")
    else:
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.metric("Total de Grupos com Duplicatas", len(duplicate_groups))
        with col_m2:
            st.metric("Registros que serão MANTIDOS", len(duplicate_groups))
        with col_m3:
            st.metric("Registros extras para APAGAR", num_dups, delta=f"-{num_dups}", delta_color="inverse")

        st.warning(f"⚠️ **Atenção:** Foram encontradas duplicatas exatas. Você pode exportar o relatório ou revisar grupo por grupo abaixo.")

        # --- SEÇÃO DE RELATÓRIO EXPORTÁVEL ---
        st.write("### 📄 Relatório de Duplicatas")
        
        # Gerar DataFrame de exportação
        export_rows = []
        for key, group_data in duplicate_groups.items():
            data_aula, horario, t_key, d_key = key
            t_name = class_options.get(t_key, t_key) if isinstance(t_key, int) else t_key
            d_name = subject_options.get(d_key, d_key) if isinstance(d_key, int) else d_key
            
            for row in group_data['all']:
                is_keep = row['id'] == group_data['keep']['id']
                export_rows.append({
                    "ID": row.get('id'),
                    "Ação Proposta": "MANTER" if is_keep else "EXCLUIR",
                    "Data Aula": row.get('data_aula'),
                    "Horário": row.get('horario'),
                    "Turma ID": row.get('turma_id'),
                    "Turma Nome": t_name,
                    "Disciplina ID": row.get('disciplina_id'),
                    "Disciplina Nome": d_name,
                    "Criado Em": row.get('created_at'),
                    "Status Registro": row.get('status')
                })
        
        df_export = pd.DataFrame(export_rows)
        csv_data = df_export.to_csv(index=False, encoding='utf-8-sig')
        
        st.download_button(
            label="📥 Baixar Relatório de Duplicatas (CSV)",
            data=csv_data,
            file_name=f"relatorio_duplicatas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

        # Detalhes das Duplicatas por Expander
        st.write("### 🔍 Detalhes dos Grupos Duplicados")
        
        for idx, (key, group_data) in enumerate(duplicate_groups.items()):
            data_aula, horario, t_key, d_key = key
            t_name = class_options.get(t_key, t_key) if isinstance(t_key, int) else t_key
            d_name = subject_options.get(d_key, d_key) if isinstance(d_key, int) else d_key
            
            header = f"📅 {data_aula} | 🕒 {horario} | 🏫 {t_name} | 📚 {d_name} ({len(group_data['all'])} registros)"
            
            with st.expander(header):
                table_rows = []
                for row in group_data['all']:
                    action = "✅ MANTER" if row['id'] == group_data['keep']['id'] else "❌ APAGAR"
                    created_formatted = ""
                    if row.get('created_at'):
                        try:
                            dt = datetime.fromisoformat(row['created_at'].replace('Z', '+00:00'))
                            created_formatted = dt.strftime("%d/%m/%Y %H:%M:%S")
                        except Exception:
                            created_formatted = row['created_at']
                            
                    table_rows.append({
                        "Ação": action,
                        "ID": row.get('id'),
                        "Data Aula": row.get('data_aula'),
                        "Horário": row.get('horario'),
                        "Turma": row.get('turma'),
                        "Disciplina": row.get('disciplina'),
                        "Status": row.get('status'),
                        "Criado em": created_formatted,
                        "Já Marcado Duplicado": "Sim" if row.get('is_duplicate') else "Não"
                    })
                
                df = pd.DataFrame(table_rows)
                st.dataframe(df, use_container_width=True, hide_index=True)

        # Seção de Ações de Limpeza
        st.write("---")
        st.write("### 🛡️ Executar Limpeza Segura")
        
        st.markdown(f"""
        Esta ação apagará permanentemente apenas os **{num_dups} registros extras** identificados como cópias duplicadas com base nos filtros selecionados.
        """)

        # Checkbox de Confirmação Obrigatória
        confirm_checkbox = st.checkbox(
            f"Eu revisei a lista de duplicatas acima e confirmo que desejo excluir os {num_dups} registros duplicados extras.",
            value=False
        )

        # Botão de Execução
        if st.button("🗑️ Excluir Duplicatas Permanentemente", disabled=not confirm_checkbox, type="primary"):
            ids_to_delete = [r['id'] for r in records_to_delete]
            
            try:
                with st.spinner(f"Removendo {num_dups} duplicatas do banco de dados..."):
                    # Executa a deleção
                    res_del = supabase.table("historico_aulas").delete().in_("id", ids_to_delete).execute()
                    
                    # --- GRAVAR HISTÓRICO DE LOGS ---
                    log_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "usuario": "Administrador (Painel)",
                        "turma_filtrada": selected_class_name,
                        "disciplina_filtrada": selected_subject_name,
                        "estrategia_usada": strategy,
                        "registros_excluidos": num_dups,
                        "ids_excluidos": ids_to_delete
                    }
                    
                    history = []
                    if os.path.exists(cleanup_history_file):
                        try:
                            with open(cleanup_history_file, "r", encoding="utf-8") as hf:
                                history = json.load(hf)
                        except Exception:
                            pass
                            
                    history.insert(0, log_entry) # insere no início (mais recente primeiro)
                    
                    with open(cleanup_history_file, "w", encoding="utf-8") as hf:
                        json.dump(history, hf, indent=4, ensure_ascii=False)
                    
                    st.success(f"🎉 **Sucesso!** {num_dups} registros duplicados foram excluídos com segurança e a ação foi logada.")
                    st.cache_data.clear()
                    st.balloons()
            except Exception as e:
                st.error(f"Erro ao executar a exclusão: {e}")

# --- HISTÓRICO DE LIMPEZAS REALIZADAS (LOGS) ---
st.write("---")
st.write("### 📜 Histórico de Deletações e Logs de Auditoria")

if os.path.exists(cleanup_history_file):
    try:
        with open(cleanup_history_file, "r", encoding="utf-8") as hf:
            history_data = json.load(hf)
            
        if len(history_data) == 0:
            st.info("Nenhuma limpeza registrada no histórico local de logs ainda.")
        else:
            display_history = []
            for h in history_data:
                # Formatar data legível
                dt_log = datetime.fromisoformat(h['timestamp']).strftime("%d/%m/%Y %H:%M:%S")
                display_history.append({
                    "Data/Hora": dt_log,
                    "Usuário": h['usuario'],
                    "Filtro Turma": h['turma_filtrada'],
                    "Filtro Disciplina": h['disciplina_filtrada'],
                    "Estratégia": h['estrategia_usada'],
                    "Qtd Apagada": f"{h['registros_excluidos']} registros"
                })
            
            df_history = pd.DataFrame(display_history)
            st.dataframe(df_history, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Erro ao carregar os logs de histórico: {e}")
else:
    st.info("Nenhum histórico de limpeza foi registrado ainda neste servidor.")

# Adicionar um botão para carregar o plugin (opcional)
st.sidebar.markdown("---")
st.sidebar.title("🔌 Carregar Plugin")
if st.sidebar.button("Carregar Plugin"):
    st.write("Plugin carregado com sucesso!")
