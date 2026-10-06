"""
headless_worker.py — Modo headless do SentPrint.

Roda sem interface grafica (QCoreApplication) via Task Scheduler.
Monitora a inbox e imprime automaticamente.
Encerra graciosamente quando a interface grafica assume o controle.
"""
import os
import sys
import logging

from PySide6.QtCore import QCoreApplication, QTimer

import config
import print_helper
from watcher import EventosWatcher

# ── Caminhos de controle ─────────────────────────────────────────────
_APP_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SentPrint"
)
os.makedirs(_APP_DIR, exist_ok=True)

PID_FILE  = os.path.join(_APP_DIR, "headless.pid")      # PID do processo headless
LOG_FILE  = os.path.join(_APP_DIR, "headless.log")      # log em disco
STOP_FILE = os.path.join(_APP_DIR, "gui_running.flag")  # sinal: GUI assumiu controle


# ── Helpers de PID ───────────────────────────────────────────────────

def _escrever_pid():
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def _remover_pid():
    try:
        os.remove(PID_FILE)
    except Exception:
        pass


# ── Setup de log em arquivo ──────────────────────────────────────────

def _setup_log():
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        encoding="utf-8",
    )


# ── Entry point do modo headless ─────────────────────────────────────

def rodar_headless() -> int:
    """
    Inicializa o modo headless e bloqueia ate encerrar.
    Retorna o exit code do QCoreApplication.
    """
    _setup_log()
    _escrever_pid()
    logging.info("=" * 60)
    logging.info("SentPrint headless iniciado (PID %s).", os.getpid())

    app = QCoreApplication(sys.argv)
    app.setApplicationName("SentPrint-Headless")

    # ── Watcher ─────────────────────────────────────────────────────
    watcher = EventosWatcher()

    def ao_receber_evento(evento: dict):
        itens = evento.get("extra", {}).get("itens", [])
        de_display = evento.get("de_display") or evento.get("de") or "?"
        path = evento.get("_path", "")

        if not itens:
            logging.warning("Evento de '%s' sem itens — ignorado.", de_display)
            return

        impressora = config.obter_impressora_padrao()
        ok, msg = print_helper.imprimir_itens(itens, impressora=impressora)

        if ok:
            logging.info(
                "%s enviou %d item(ns) -> %s", de_display, len(itens), msg
            )
        else:
            logging.error(
                "FALHA — %s enviou %d item(ns): %s", de_display, len(itens), msg
            )

        if path:
            watcher.marcar_lida(path)

    def ao_erro(msg: str):
        logging.error("[watcher] %s", msg)

    watcher.novo_evento.connect(ao_receber_evento)
    watcher.erro.connect(ao_erro)

    # ── Iniciar monitoramento ────────────────────────────────────────
    pasta   = config.obter_pasta_compartilhada()
    usuario = config.obter_usuario()

    if pasta and usuario:
        watcher.iniciar(usuario, pasta)
        logging.info("Monitorando — usuario: %s | pasta: %s", usuario, pasta)
    else:
        logging.warning(
            "Configuracao incompleta (pasta=%r, usuario=%r). "
            "Configure pelo modo grafico e reinicie.",
            pasta, usuario,
        )

    # ── Timer de verificacao de parada ───────────────────────────────
    # Verifica a cada 2s se a GUI sinalizou que quer assumir o controle.
    def verificar_stop():
        if os.path.exists(STOP_FILE):
            logging.info("GUI assumiu controle — encerrando headless.")
            watcher.parar()
            _remover_pid()
            app.quit()

    stop_timer = QTimer()
    stop_timer.setInterval(2000)
    stop_timer.timeout.connect(verificar_stop)
    stop_timer.start()

    exit_code = app.exec()

    # Limpeza final (caso encerrado por outro motivo)
    watcher.parar()
    _remover_pid()
    logging.info("SentPrint headless encerrado (exit %d).", exit_code)
    return exit_code
