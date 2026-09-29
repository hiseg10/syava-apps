"""Downloader do portal SeducTec (PDFs + links de vídeo).

Porte do script legado `Aulas_selenium/tools/utils/seductec_scraper.py` para uso
dentro do Streamlit: sem `input()`, sem `print()` — tudo é reportado via
`on_log(msg)` e `on_progress(...)`.

Destino: `<projeto>/data/repo/<turma>/<disciplina>/<S0X>/seductec/`
"""

from __future__ import annotations

import os
import re
import threading
import time
import unicodedata
from typing import Callable, Iterable, Optional

import requests
from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
REPO_BASE = os.path.join(PROJECT_ROOT, "data", "repo")
PORTAL_HOME = "https://seductec.seduc.pi.gov.br/"
PORTAL_LOGIN = "https://seductec.seduc.pi.gov.br/login/index.php"
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".chrome_profile")

SECTION_PATTERN = re.compile(r"S(\d+)-AULA\s*(\d+)", re.IGNORECASE)
YT_PATTERNS = [
    r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
    r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
    r"youtu\.be/([a-zA-Z0-9_-]{11})",
    r"video_id[\"']:\s*[\"']([^\"']+)[\"']",
]

LogFn = Callable[[str], None]
ProgressFn = Callable[[int, int, str], None]


def _noop(*_args, **_kwargs) -> None:
    return None


def normalize(text: str) -> str:
    """Chave de comparação: sem acentos, sem caixa, sem pontuação extra."""
    if not text:
        return ""
    stripped = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", " ", stripped).strip().upper()


def clean_folder_name(name: str) -> str:
    """Converte o nome do portal em nome de pasta legível."""
    clean = "".join(c if (c.isalnum() or c in " -_") else " " for c in name)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:60] or "SEM_NOME"


def build_dest_dir(turma: str, disciplina: str, semana: str, pasta: str = "seductec") -> str:
    return os.path.join(REPO_BASE, turma, disciplina, semana, pasta)


def suggest_disciplina(curso_nome: str, turma: str, extra: Iterable[str] = ()) -> str:
    """Casa o nome do curso do portal com pastas já existentes da turma."""
    alvo = normalize(curso_nome)
    candidatos: list[str] = list(extra)
    base_turma = os.path.join(REPO_BASE, turma)
    if os.path.isdir(base_turma):
        candidatos.extend(os.listdir(base_turma))
    for pasta in sorted(set(candidatos)):
        if not alvo:
            break
        chave = normalize(pasta)
        if alvo and (alvo in chave or chave in alvo):
            return pasta
    return clean_folder_name(curso_nome)


class SeductecDownloader:
    """Sessão de navegador + download. Um download por vez."""

    def __init__(
        self,
        on_log: Optional[LogFn] = None,
        on_progress: Optional[ProgressFn] = None,
        keep_session: bool = True,
    ):
        self.on_log: LogFn = on_log or _noop
        self.on_progress: ProgressFn = on_progress or _noop
        self.keep_session = keep_session
        self.driver = None
        self.wait: Optional[WebDriverWait] = None
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            }
        )
        self.courses: list[dict] = []
        self.login_ok = False
        self.stats = {"pdfs": 0, "pulados": 0, "erros": 0, "aulas": 0}
        self._stop = threading.Event()

    # ---------------------------------------------------------------- driver
    def start_browser(self) -> None:
        if self.driver is not None:
            return
        options = Options()
        options.add_argument("--start-maximized")
        if self.keep_session:
            options.add_argument(f"--user-data-dir={PROFILE_DIR}")
            options.add_argument("--profile-directory=SeducTec")
        self.on_log("Abrindo o Chrome... faça o login no portal (CAPTCHA).")
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_page_load_timeout(60)
        self.wait = WebDriverWait(self.driver, 20)
        self._get(PORTAL_LOGIN)

    def _get(self, url: str) -> None:
        try:
            self.driver.get(url)
        except (WebDriverException, ConnectionResetError) as exc:
            self.on_log(f"Alerta ao abrir {url}: {str(exc)[:100]}")

    def stop_browser(self) -> None:
        self._stop.set()
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:  # noqa: BLE001
                pass
            self.driver = None
            self.wait = None
        self.login_ok = False

    # ----------------------------------------------------------------- login
    def wait_for_login(self, timeout: int = 600, interval: float = 2.0) -> bool:
        """Aguarda o login manual sem usar input().

        Considera logado quando a URL sai de /login/index.php **e** a página
        inicial mostra a lista de cursos (`.coursename`).
        """
        deadline = time.time() + timeout
        while time.time() < deadline and not self._stop.is_set():
            if self.check_login_now():
                return True
            time.sleep(interval)
        self.on_log("Tempo esgotado aguardando o login.")
        return False

    def check_login_now(self) -> bool:
        """Checagem única, não bloqueante (para o fragmento do Streamlit)."""
        if self.login_ok:
            return True
        try:
            url = (self.driver.current_url or "").lower()
            if "login/index.php" in url:
                return False
            self.driver.find_elements(By.CLASS_NAME, "coursename")
        except Exception:  # noqa: BLE001
            return False
        self.login_ok = True
        self._sync_cookies()
        self.on_log("Login detectado. Sessão pronta.")
        return True

    def force_logged_in(self) -> bool:
        """Checagem rápida de login usada pela UI a cada segundo."""
        return self.check_login_now()

    def _sync_cookies(self) -> None:
        try:
            for cookie in self.driver.get_cookies():
                self.session.cookies.set(cookie["name"], cookie["value"])
        except Exception as exc:  # noqa: BLE001
            self.on_log(f"Falha ao copiar cookies: {exc}")

    # ----------------------------------------------------------------- cursos
    def list_courses(self) -> list[dict]:
        self._get(PORTAL_HOME)
        try:
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "coursename")))
        except TimeoutException:
            self.on_log("Portal não respondeu listando disciplinas.")
            return []
        cursos = []
        for el in self.driver.find_elements(By.CLASS_NAME, "coursename"):
            nome = (el.text or "").strip()
            url = el.get_attribute("href")
            if nome and url:
                cursos.append({"nome": nome, "url": url})
        self.courses = cursos
        self.on_log(f"{len(cursos)} disciplina(s) encontrada(s).")
        return cursos

    # ------------------------------------------------------------ extração
    def collect_tasks(self, course_url: str) -> list[dict]:
        self._get(course_url)
        try:
            self.wait.until(EC.presence_of_element_located((By.ID, "multi_section_tiles")))
        except TimeoutException:
            self.on_log("Página da disciplina não carregou (timeout nos tiles).")
            return []
        tasks = []
        for tile in self.driver.find_elements(By.CSS_SELECTOR, "li.tile a.tile-link"):
            label = tile.get_attribute("aria-label") or ""
            match = SECTION_PATTERN.search(label)
            if not match:
                continue
            tasks.append(
                {
                    "semana": f"S{int(match.group(1)):02d}",
                    "aula": f"Aula_{int(match.group(2)):02d}",
                    "url": tile.get_attribute("href"),
                }
            )
        tasks.sort(key=lambda t: (t["semana"], t["aula"]))
        self.on_log(f"{len(tasks)} aula(s) localizada(s) na disciplina.")
        return tasks

    def process_course(self, course_url: str, turma: str, disciplina: str) -> dict:
        tasks = self.collect_tasks(course_url)
        if not tasks:
            return dict(self.stats)
        total = len(tasks)
        self.stats = {"pdfs": 0, "pulados": 0, "erros": 0, "aulas": total}
        for i, task in enumerate(tasks, 1):
            if self._stop.is_set():
                break
            self.on_progress(i, total, f"{task['semana']} / {task['aula']}")
            self._process_lesson(task, turma, disciplina)
        self.on_log(
            f"Concluído: {self.stats['pdfs']} PDF(s) novos, "
            f"{self.stats['pulados']} já existente(s), {self.stats['erros']} erro(s)."
        )
        return dict(self.stats)

    def _process_lesson(self, task: dict, turma: str, disciplina: str) -> None:
        try:
            self._get(task["url"])
            self.wait.until(EC.presence_of_element_located((By.ID, "region-main")))
            time.sleep(2)
        except Exception as exc:  # noqa: BLE001
            self.on_log(f"  Erro ao abrir {task['aula']}: {exc}")
            return

        dest = build_dest_dir(turma, disciplina, task["semana"])
        os.makedirs(dest, exist_ok=True)

        pdf_urls = self._find_pdfs()
        for idx, url in enumerate(pdf_urls, 1):
            self._download_pdf(url, dest, f"{task['aula']}_Parte_{idx}.pdf")

        yt_links = self._find_videos()
        self._write_links(dest, disciplina, task["aula"], yt_links)

    def _find_pdfs(self) -> list[str]:
        container = self.driver.find_element(By.ID, "region-main")
        found: list[str] = []
        for el in container.find_elements(
            By.CSS_SELECTOR, "a[href*='/resource/view.php'], a.cm-link"
        ):
            try:
                if not el.is_displayed():
                    continue
                href = el.get_attribute("href") or ""
                if "/resource/view.php" not in href:
                    continue
                inner = (el.get_attribute("innerHTML") or "").lower()
                if any(k in inner for k in ("pdf", "leitura", "aula")):
                    found.append(href)
            except Exception:  # noqa: BLE001
                continue
        return list(dict.fromkeys(found))

    def _find_videos(self) -> list[str]:
        links: set[str] = set()

        for iframe in self.driver.find_elements(By.TAG_NAME, "iframe"):
            try:
                src = iframe.get_attribute("src") or ""
                if "youtube.com" in src or "youtu.be" in src:
                    links.add(src)
                self.driver.switch_to.frame(iframe)
                page = self.driver.page_source
                for pattern in YT_PATTERNS:
                    for vid in re.findall(pattern, page):
                        links.add(f"https://www.youtube.com/watch?v={vid}")
                self.driver.switch_to.default_content()
            except Exception:  # noqa: BLE001
                try:
                    self.driver.switch_to.default_content()
                except Exception:  # noqa: BLE001
                    pass

        page = self.driver.page_source
        for pattern in YT_PATTERNS:
            for vid in re.findall(pattern, page):
                links.add(f"https://www.youtube.com/watch?v={vid}")

        for el in self.driver.find_elements(By.CSS_SELECTOR, "a"):
            try:
                href = el.get_attribute("href") or ""
                if any(
                    x in href
                    for x in (
                        "youtube.com/watch",
                        "youtu.be/",
                        "youtube.com/v/",
                        "youtube.com/shorts/",
                    )
                ):
                    links.add(href)
                elif "/mod/url/view.php" in href or "/mod/page/view.php" in href:
                    video = self._check_moodle_video(href)
                    if video:
                        links.add(video)
            except Exception:  # noqa: BLE001
                continue
        return sorted(links)

    def _check_moodle_video(self, moodle_url: str) -> Optional[str]:
        try:
            resp = self.session.get(moodle_url, allow_redirects=True, timeout=10)
            if "youtube.com" in resp.url or "youtu.be" in resp.url:
                return resp.url
            for pattern in YT_PATTERNS:
                match = re.search(pattern, resp.text)
                if match:
                    return f"https://www.youtube.com/watch?v={match.group(1)}"
        except Exception:  # noqa: BLE001
            pass
        return None

    # -------------------------------------------------------------- downloads
    def _download_pdf(self, moodle_url: str, dest_folder: str, filename: str) -> None:
        path = os.path.join(dest_folder, filename)
        try:
            response = self.session.get(moodle_url, allow_redirects=True, timeout=20)
            content_type = response.headers.get("Content-Type", "")

            if "application/pdf" in content_type:
                self._save(path, filename, response.content)
                return

            match = re.search(
                r'https?://seductec\.seduc\.pi\.gov\.br/[^"]+pluginfile\.php/[^"]+\.pdf[^"]*',
                response.text,
            )
            if match:
                real_url = match.group(0).replace("&amp;", "&")
                pdf_resp = self.session.get(real_url, timeout=20)
                if "application/pdf" in pdf_resp.headers.get("Content-Type", ""):
                    self._save(path, filename, pdf_resp.content)
                    return

            match_forced = re.search(
                r'https?://seductec\.seduc\.pi\.gov\.br/[^"]+forcedownload=1',
                response.text,
            )
            if match_forced:
                real_url = match_forced.group(0).replace("&amp;", "&")
                pdf_resp = self.session.get(real_url, timeout=20)
                self._save(path, filename, pdf_resp.content)
                return
            self.on_log(f"    Não identifiquei o PDF em: {filename}")
        except Exception as exc:  # noqa: BLE001
            self.stats["erros"] += 1
            self.on_log(f"    Erro ao baixar {filename}: {exc}")

    def _save(self, path: str, filename: str, content: bytes) -> None:
        if os.path.exists(path) and len(content) == os.path.getsize(path):
            self.stats["pulados"] += 1
            self.on_log(f"    Já existe: {filename}")
            return
        with open(path, "wb") as fh:
            fh.write(content)
        self.stats["pdfs"] += 1
        self.on_log(f"    PDF salvo: {filename}")

    def _write_links(
        self, dest_folder: str, disciplina: str, aula: str, links: list[str]
    ) -> None:
        """Reescreve `links_aulas.md` por completo (idempotente, sem duplicar)."""
        md_path = os.path.join(dest_folder, "links_aulas.md")
        entradas: dict[str, list[str]] = {}
        if os.path.exists(md_path):
            entradas = self._parse_links_md(md_path)

        entradas[aula] = [
            link.replace("/embed/", "/watch?v=") for link in sorted(set(links))
        ]
        entradas = {k: v for k, v in entradas.items() if v}
        if not entradas:
            return

        linhas = [f"# Links de Vídeo - {disciplina}", ""]
        for nome in sorted(entradas):
            linhas.append(f"### {nome}")
            for link in entradas[nome]:
                linhas.append(f"- [Vídeo da Aula]({link})")
            linhas.append("")
        tmp_path = md_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(linhas))
        os.replace(tmp_path, md_path)
        self.on_log("    Links gravados em links_aulas.md")

    @staticmethod
    def _parse_links_md(path: str) -> dict[str, list[str]]:
        entradas: dict[str, list[str]] = {}
        atual: Optional[str] = None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for linha in fh:
                    linha = linha.rstrip()
                    if linha.startswith("### "):
                        atual = linha[4:].strip()
                        entradas.setdefault(atual, [])
                    elif linha.startswith("- [") and atual:
                        inicio = linha.find("(")
                        fim = linha.rfind(")")
                        if inicio != -1 and fim > inicio:
                            entradas[atual].append(linha[inicio + 1 : fim])
        except OSError:
            return {}
        return entradas
