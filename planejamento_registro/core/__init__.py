"""Núcleo do app de Planejamento e Registro.

Módulos independentes da API (sem FastAPI):

- ``banco``   : conexão SQLite, configuração, frequência e IDs de disciplina.
- ``datas``   : parsing de datas e regras de calendário/corte.
- ``gerador`` : geração dos arquivos .txt de plano de aula.

Tanto o app Streamlit quanto o endpoint da API reutilizam estes módulos.
"""
