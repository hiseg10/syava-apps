import os
import sys
import threading

import streamlit as st

# Raiz do projeto SysAva (imports de services.*)
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from apps.down_seductec.seductec_downloader import (
        REPO_BASE,
        SeductecDownloader,
        build_dest_dir,
        suggest_disciplina,
    )
except ImportError as e:
    st.error(f"Erro de importação: {e}")
    st.stop()

try:
    import services.database as db
except Exception:  # noqa: BLE001 - offline/sem credenciais não impede o app
    db = None

st.set_page_config(
    page_title="Downloader SeducTec",
    page_icon="📥",
    layout="wide",
)

st.title("📥 Downloader de Aulas SeducTec")
st.caption(
    "Baixa PDFs e links de vídeo do portal SeducTec para "
    "`data/repo/<turma>/<disciplina>/S0X/seductec/`."
)

# Estado compartilhado com as threads (st.session_state não é confiável fora
# do contexto de execução do Streamlit). Guardado no session_state para
# sobreviver aos reruns do Streamlit.
RUNTIME = st.session_state.setdefault(
    "down_runtime",
    {
        "logs": [],
        "progress": (0, 1, ""),
        "stats": None,
        "running": False,   # download em andamento
        "connecting": False,  # navegador abrindo
        "courses": None,
    },
)
# Sessões antigas podem não ter as chaves novas
RUNTIME.setdefault("running", False)
RUNTIME.setdefault("connecting", False)


def log(msg: str) -> None:
    RUNTIME["logs"].append(str(msg))
    if len(RUNTIME["logs"]) > 400:
        del RUNTIME["logs"][:-400]


def progress(atual: int, total: int, rotulo: str) -> None:
    RUNTIME["progress"] = (atual, total, rotulo)


def get_downloader() -> SeductecDownloader:
    if "down_loader" not in st.session_state:
        st.session_state.down_loader = SeductecDownloader(
            on_log=log, on_progress=progress, keep_session=True
        )
    return st.session_state.down_loader


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_turmas() -> list[str]:
    if db is None:
        return []
    try:
        return [c["name"] for c in db.get_classes() if c.get("name")]
    except Exception:  # noqa: BLE001
        return []


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Configuração")
    turmas = get_turmas()
    if turmas:
        turma = st.selectbox("Turma (destino)", turmas)
    else:
        turma = st.text_input("Turma (destino)", value="3_DS")
    keep = st.checkbox("Relembrar sessão do portal", value=True)
    st.markdown(f"**Base:** `{REPO_BASE}`")

    st.divider()
    loader = st.session_state.get("down_loader")
    conectado = loader is not None and loader.driver is not None

    if not conectado:
        if RUNTIME["connecting"]:
            st.button("⏳ Abrindo o navegador...", disabled=True, use_container_width=True)
        elif st.button("🌐 Conectar ao portal", type="primary", use_container_width=True):
            loader = get_downloader()
            loader.keep_session = keep
            RUNTIME["connecting"] = True
            RUNTIME["running"] = False
            RUNTIME["courses"] = None
            RUNTIME["logs"] = []
            RUNTIME["stats"] = None
            RUNTIME["progress"] = (0, 1, "")
            log("Abrindo navegador... faça o login (CPF/senha + CAPTCHA).")

            def _abrir():
                try:
                    loader.start_browser()
                except Exception as exc:  # noqa: BLE001
                    log(f"Erro ao abrir o navegador: {exc}")
                finally:
                    RUNTIME["connecting"] = False

            threading.Thread(target=_abrir, daemon=True).start()
            st.rerun()
    else:
        if st.button("🔌 Desconectar", use_container_width=True):
            get_downloader().stop_browser()
            RUNTIME["running"] = False
            RUNTIME["courses"] = None
            RUNTIME["stats"] = None
            st.rerun()


# --------------------------------------------------------------- fragmento
@st.fragment(run_every=1)
def _live():
    loader = st.session_state.get("down_loader")
    if loader is not None and loader.driver is not None and not loader.login_ok:
        if loader.force_logged_in():
            RUNTIME["courses"] = None

    atual, total, rotulo = RUNTIME["progress"]
    if RUNTIME["running"] and total > 1:
        st.progress(min(atual / total, 1.0), text=f"{atual}/{total} — {rotulo}")

    with st.container(height=300):
        if RUNTIME["logs"]:
            st.code("\n".join(RUNTIME["logs"][-40:]), language="text")
        else:
            st.caption("Log do download aparece aqui.")
    if RUNTIME["stats"]:
        st.json(RUNTIME["stats"])


_live()

loader = st.session_state.get("down_loader")
pronto = loader is not None and loader.driver is not None and loader.login_ok

if not pronto:
    st.info(
        "Clique em **Conectar ao portal** na barra lateral e faça o login. "
        "O app detecta sozinho quando você estiver dentro."
    )
    st.stop()

# ------------------------------------------------------------------ cursos
col_a, col_b = st.columns([2, 1])

with col_a:
    if st.button(
        "🔄 Listar disciplinas",
        use_container_width=True,
        disabled=RUNTIME["running"] or RUNTIME["connecting"],
    ):
        with st.spinner("Buscando disciplinas no portal..."):
            RUNTIME["courses"] = loader.list_courses()
        if not RUNTIME["courses"]:
            st.warning("Nenhuma disciplina encontrada nesta conta.")

    cursos = RUNTIME["courses"] or []
    if not cursos:
        st.stop()

    selecao = st.multiselect(
        "Disciplinas para baixar",
        options=[c["nome"] for c in cursos],
    )

    pares = []
    for nome in selecao:
        url = next((c["url"] for c in cursos if c["nome"] == nome), None)
        if not url:
            continue
        destino = st.text_input(
            f"Pasta da disciplina — {nome}",
            value=suggest_disciplina(nome, turma),
            key=f"dest_{nome}",
        )
        pares.append({"nome": nome, "url": url, "pasta": destino})

with col_b:
    st.markdown("**Destino de exemplo**")
    if pares:
        st.code(build_dest_dir(turma, pares[0]["pasta"], "S01"), language="text")

    if pares and st.button(
        "⬇️ Baixar selecionadas",
        type="primary",
        disabled=RUNTIME["running"],
        use_container_width=True,
    ):
        RUNTIME["running"] = True
        RUNTIME["stats"] = None
        RUNTIME["progress"] = (0, 1, "")

        def _job():
            total_stats = {"pdfs": 0, "pulados": 0, "erros": 0, "aulas": 0}
            try:
                for par in pares:
                    log(f"--- {par['nome']} → {par['pasta']} ---")
                    stats = loader.process_course(par["url"], turma, par["pasta"])
                    for key in total_stats:
                        total_stats[key] += stats.get(key, 0)
                RUNTIME["stats"] = total_stats
            except Exception as exc:  # noqa: BLE001
                log(f"Erro geral: {exc}")
            finally:
                RUNTIME["running"] = False

        threading.Thread(target=_job, daemon=True).start()
        st.rerun()

    if RUNTIME["running"]:
        st.warning("Download em andamento...")

if RUNTIME["stats"] and not RUNTIME["running"]:
    st.caption(f"Arquivos em `{os.path.join(REPO_BASE, turma)}`")
    if os.path.isdir(os.path.join(REPO_BASE, turma)):
        if st.button("📁 Abrir pasta da turma"):
            os.startfile(os.path.join(REPO_BASE, turma))
