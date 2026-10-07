"""
main_window.py — Janela principal do SentPrint.
Fica rodando na bandeja, monitora a inbox e imprime automaticamente.
"""
import os
import json
import time
import subprocess
from datetime import datetime

# ── Caminhos de controle (espelho do headless_worker.py) ────────────
_APP_DIR_CTRL = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SentPrint"
)
os.makedirs(_APP_DIR_CTRL, exist_ok=True)
_PID_FILE  = os.path.join(_APP_DIR_CTRL, "headless.pid")
_STOP_FILE = os.path.join(_APP_DIR_CTRL, "gui_running.flag")


def _assumir_controle_do_headless():
    """Sinaliza o processo headless para encerrar e aguarda sua saida."""
    # 1. Cria flag de parada (headless verifica a cada 2s)
    try:
        open(_STOP_FILE, "w").close()
    except Exception:
        pass

    # 2. Mata o processo diretamente pelo PID (mais rapido que esperar 2s)
    if os.path.exists(_PID_FILE):
        try:
            with open(_PID_FILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
            )
        except Exception:
            pass
        # Aguarda ate o PID file ser removido (max 3s)
        for _ in range(30):
            if not os.path.exists(_PID_FILE):
                break
            time.sleep(0.1)
        # Remove residual se headless nao apagou
        try:
            os.remove(_PID_FILE)
        except Exception:
            pass

import qtawesome
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QLineEdit, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QFrame, QSystemTrayIcon, QMenu,
    QSizePolicy, QApplication,
)
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QColor, QFont
from PySide6.QtPrintSupport import QPrinterInfo

import config
import print_helper
from watcher import EventosWatcher

# ------------------------------------------------------------------
# Helpers de estilo
# ------------------------------------------------------------------
STATUS_AGUARDANDO = "aguardando"
STATUS_ATIVO      = "ativo"
STATUS_ERRO       = "erro"

_STATUS_COLOR = {
    STATUS_AGUARDANDO: "#f59e0b",
    STATUS_ATIVO:      "#10b981",
    STATUS_ERRO:       "#ef4444",
}
_STATUS_LABEL = {
    STATUS_AGUARDANDO: "Aguardando configuracao...",
    STATUS_ATIVO:      "Monitorando...",
    STATUS_ERRO:       "Erro — verifique as configuracoes",
}

MAX_LOG = 200   # linhas maximas no historico


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SentPrint")
        self.setMinimumSize(580, 560)
        self.resize(680, 620)

        self._watcher = EventosWatcher(self)
        self._watcher.novo_evento.connect(self._ao_receber_evento)
        self._watcher.erro.connect(lambda msg: self._log(f"[ERRO watcher] {msg}", erro=True))

        self._status_atual = STATUS_AGUARDANDO
        self._log_entries = []  # lista de (ts_str, texto, erro)

        # Assume controle do processo headless (se estiver rodando)
        _assumir_controle_do_headless()

        self._setup_ui()
        self._setup_tray()
        self._aplicar_styles()
        self._carregar_config()

        # pulsa o dot de status a cada segundo
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(1000)
        self._pulse_timer.timeout.connect(self._pulse_status)
        self._pulse_timer.start()
        self._pulse_state = True

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _setup_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(72)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(24, 0, 24, 0)
        h_lay.setSpacing(14)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(qtawesome.icon("fa6s.print", color="#6366f1").pixmap(28, 28))
        h_lay.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        lbl_title = QLabel("SentPrint")
        lbl_title.setObjectName("appTitle")
        title_col.addWidget(lbl_title)
        lbl_sub = QLabel("Receptor de impressao automatica")
        lbl_sub.setObjectName("appSub")
        title_col.addWidget(lbl_sub)
        h_lay.addLayout(title_col)
        h_lay.addStretch()

        # status pill
        self.dot_status = QLabel("●")
        self.dot_status.setObjectName("dotStatus")
        self.lbl_status = QLabel(_STATUS_LABEL[STATUS_AGUARDANDO])
        self.lbl_status.setObjectName("lblStatus")
        h_lay.addWidget(self.dot_status)
        h_lay.addWidget(self.lbl_status)

        root.addWidget(header)

        # ── Separador ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        root.addWidget(sep)

        # ── Conteudo ──
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(24, 20, 24, 20)
        body_lay.setSpacing(16)
        root.addWidget(body, 1)

        # ── Card: Configuracao ──
        card_cfg = self._make_card()
        cfg_lay = QVBoxLayout(card_cfg)
        cfg_lay.setContentsMargins(20, 16, 20, 16)
        cfg_lay.setSpacing(12)

        lbl_cfg_title = QLabel("Configuracao")
        lbl_cfg_title.setObjectName("cardTitle")
        cfg_lay.addWidget(lbl_cfg_title)

        # -- Usuario
        row_u = QHBoxLayout()
        row_u.setSpacing(8)
        lbl_u = QLabel("Usuario:")
        lbl_u.setFixedWidth(130)
        lbl_u.setObjectName("fieldLabel")
        self.combo_usuarios = QComboBox()
        self.combo_usuarios.setFixedHeight(34)
        self.combo_usuarios.setEditable(False)
        self.combo_usuarios.setPlaceholderText("Selecione o usuario...")
        self.combo_usuarios.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_usuarios.currentIndexChanged.connect(self._ao_mudar_usuario)
        row_u.addWidget(lbl_u)
        row_u.addWidget(self.combo_usuarios)
        cfg_lay.addLayout(row_u)

        # -- Pasta compartilhada
        row_p = QHBoxLayout()
        row_p.setSpacing(8)
        lbl_p = QLabel("Pasta compartilhada:")
        lbl_p.setFixedWidth(130)
        lbl_p.setObjectName("fieldLabel")
        self.campo_pasta = QLineEdit()
        self.campo_pasta.setPlaceholderText("Ex: S:\\")
        self.campo_pasta.setFixedHeight(34)
        self.campo_pasta.setReadOnly(True)
        self.campo_pasta.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_pasta = QPushButton(qtawesome.icon("fa6s.folder-open", color="#6366f1"), "")
        btn_pasta.setFixedSize(34, 34)
        btn_pasta.setObjectName("btnIcon")
        btn_pasta.setToolTip("Selecionar pasta")
        btn_pasta.clicked.connect(self._selecionar_pasta)
        row_p.addWidget(lbl_p)
        row_p.addWidget(self.campo_pasta)
        row_p.addWidget(btn_pasta)
        cfg_lay.addLayout(row_p)

        # -- Impressora
        row_i = QHBoxLayout()
        row_i.setSpacing(8)
        lbl_i = QLabel("Impressora:")
        lbl_i.setFixedWidth(130)
        lbl_i.setObjectName("fieldLabel")
        self.combo_impressoras = QComboBox()
        self.combo_impressoras.setFixedHeight(34)
        self.combo_impressoras.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_impressoras.setPlaceholderText("Selecione a impressora...")
        btn_reload_imp = QPushButton(qtawesome.icon("fa6s.rotate", color="#6366f1"), "")
        btn_reload_imp.setFixedSize(34, 34)
        btn_reload_imp.setObjectName("btnIcon")
        btn_reload_imp.setToolTip("Recarregar impressoras")
        btn_reload_imp.clicked.connect(self._carregar_impressoras)
        self.combo_impressoras.currentIndexChanged.connect(self._ao_mudar_impressora)
        row_i.addWidget(lbl_i)
        row_i.addWidget(self.combo_impressoras)
        row_i.addWidget(btn_reload_imp)
        cfg_lay.addLayout(row_i)

        # -- Botao iniciar / parar
        row_btn = QHBoxLayout()
        row_btn.setSpacing(8)
        row_btn.addStretch()
        self.btn_iniciar = QPushButton(qtawesome.icon("fa6s.play", color="#ffffff"), "  Iniciar monitoramento")
        self.btn_iniciar.setObjectName("btnStart")
        self.btn_iniciar.setFixedHeight(36)
        self.btn_iniciar.clicked.connect(self._iniciar_monitoramento)
        self.btn_parar = QPushButton(qtawesome.icon("fa6s.stop", color="#ffffff"), "  Parar")
        self.btn_parar.setObjectName("btnStop")
        self.btn_parar.setFixedHeight(36)
        self.btn_parar.setEnabled(False)
        self.btn_parar.clicked.connect(self._parar_monitoramento)
        row_btn.addWidget(self.btn_iniciar)
        row_btn.addWidget(self.btn_parar)
        cfg_lay.addLayout(row_btn)

        body_lay.addWidget(card_cfg)

        # ── Card: Historico ──
        card_log = self._make_card()
        log_lay = QVBoxLayout(card_log)
        log_lay.setContentsMargins(20, 14, 20, 14)
        log_lay.setSpacing(8)

        row_log_title = QHBoxLayout()
        lbl_log_title = QLabel("Historico de impressoes")
        lbl_log_title.setObjectName("cardTitle")
        row_log_title.addWidget(lbl_log_title)
        row_log_title.addStretch()
        self.lbl_total = QLabel("0 impressoes")
        self.lbl_total.setObjectName("lblTotal")
        row_log_title.addWidget(self.lbl_total)
        btn_limpar = QPushButton("Limpar")
        btn_limpar.setObjectName("btnSecondary")
        btn_limpar.setFixedHeight(28)
        btn_limpar.clicked.connect(self._limpar_log)
        row_log_title.addWidget(btn_limpar)
        log_lay.addLayout(row_log_title)

        self.list_log = QListWidget()
        self.list_log.setObjectName("listLog")
        self.list_log.setAlternatingRowColors(True)
        self.list_log.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        log_lay.addWidget(self.list_log)

        body_lay.addWidget(card_log, 1)

        # ── Footer ──
        footer = QFrame()
        footer.setObjectName("footer")
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(24, 8, 24, 8)
        lbl_info = QLabel("SentPrint — receptor de etiquetas Zebra via pasta compartilhada")
        lbl_info.setObjectName("footerLabel")
        f_lay.addWidget(lbl_info)
        f_lay.addStretch()
        btn_min = QPushButton("Minimizar para bandeja")
        btn_min.setObjectName("btnSecondary")
        btn_min.setFixedHeight(28)
        btn_min.clicked.connect(self.hide)
        f_lay.addWidget(btn_min)
        root.addWidget(footer)

    def _make_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        return card

    # ------------------------------------------------------------------
    # System Tray
    # ------------------------------------------------------------------
    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(qtawesome.icon("fa6s.print", color="#6366f1").pixmap(16, 16))  # type: ignore
        menu = QMenu()
        act_show = menu.addAction("Abrir SentPrint")
        act_show.triggered.connect(self._mostrar_janela)
        menu.addSeparator()
        act_quit = menu.addAction("Sair")
        act_quit.triggered.connect(self._sair_aplicacao)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_ativado)
        self._tray.show()

    def _tray_ativado(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._mostrar_janela()

    def _sair_aplicacao(self):
        """Encerra a GUI e remove o flag de controle do headless."""
        try:
            os.remove(_STOP_FILE)
        except Exception:
            pass
        QApplication.quit()

    def _mostrar_janela(self):
        self.showNormal()
        self.activateWindow()

    def closeEvent(self, event):
        # minimiza para bandeja em vez de fechar
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "SentPrint",
            "Ainda em execucao na bandeja do sistema.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    # ------------------------------------------------------------------
    # Configuracoes
    # ------------------------------------------------------------------
    def _carregar_config(self):
        pasta = config.obter_pasta_compartilhada()
        if pasta:
            self.campo_pasta.setText(pasta)
        self._carregar_usuarios(pasta)
        self._carregar_impressoras()
        # restaura usuario salvo
        usuario_salvo = config.obter_usuario()
        if usuario_salvo:
            for i in range(self.combo_usuarios.count()):
                if self.combo_usuarios.itemData(i) == usuario_salvo or self.combo_usuarios.itemText(i).lower() == usuario_salvo:
                    self.combo_usuarios.setCurrentIndex(i)
                    break
        # restaura impressora salva
        imp_salva = config.obter_impressora_padrao()
        if imp_salva:
            idx = self.combo_impressoras.findText(imp_salva)
            if idx >= 0:
                self.combo_impressoras.setCurrentIndex(idx)
        # auto-inicia se havia configuracao valida
        if pasta and usuario_salvo and imp_salva:
            self._iniciar_monitoramento()

    def _carregar_usuarios(self, pasta_compartilhada: str):
        """Descobre usuarios disponiveis lendo a estrutura de inbox da pasta compartilhada."""
        self.combo_usuarios.blockSignals(True)
        self.combo_usuarios.clear()
        self.combo_usuarios.addItem("Selecione o usuario...", None)
        if pasta_compartilhada and os.path.isdir(pasta_compartilhada):
            inbox_base = os.path.normpath(os.path.join(pasta_compartilhada, "Almox", "Eventos", "inbox"))
            if os.path.isdir(inbox_base):
                try:
                    pastas = sorted(os.listdir(inbox_base))
                    for nome in pastas:
                        full = os.path.join(inbox_base, nome)
                        if os.path.isdir(full):
                            self.combo_usuarios.addItem(nome, nome)
                except Exception:
                    pass
        self.combo_usuarios.blockSignals(False)

    def _carregar_impressoras(self):
        self.combo_impressoras.blockSignals(True)
        atual = self.combo_impressoras.currentText()
        self.combo_impressoras.clear()
        try:
            printers = [p.printerName() for p in QPrinterInfo.availablePrinters()]
        except Exception:
            printers = []
        for p in printers:
            self.combo_impressoras.addItem(p)
        if not printers:
            self.combo_impressoras.addItem("Nenhuma impressora encontrada")
        # reseleciona
        idx = self.combo_impressoras.findText(atual)
        if idx >= 0:
            self.combo_impressoras.setCurrentIndex(idx)
        self.combo_impressoras.blockSignals(False)

    def _selecionar_pasta(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar pasta compartilhada", self.campo_pasta.text() or "")
        if pasta:
            pasta = os.path.normpath(pasta)
            self.campo_pasta.setText(pasta)
            config.definir_pasta_compartilhada(pasta)
            self._carregar_usuarios(pasta)

    def _ao_mudar_usuario(self):
        usuario = self.combo_usuarios.currentData()
        if usuario:
            config.definir_usuario(usuario)

    def _ao_mudar_impressora(self):
        imp = self.combo_impressoras.currentText()
        if imp and imp != "Nenhuma impressora encontrada":
            config.definir_impressora_padrao(imp)

    # ------------------------------------------------------------------
    # Monitoramento
    # ------------------------------------------------------------------
    def _iniciar_monitoramento(self):
        pasta = self.campo_pasta.text().strip()
        usuario = self.combo_usuarios.currentData()
        impressora = self.combo_impressoras.currentText().strip()

        if not pasta or not os.path.isdir(pasta):
            QMessageBox.warning(self, "Configuracao", "Selecione uma pasta compartilhada valida.")
            return
        if not usuario:
            QMessageBox.warning(self, "Configuracao", "Selecione o usuario (inbox para monitorar).")
            return
        if not impressora or impressora == "Nenhuma impressora encontrada":
            QMessageBox.warning(self, "Configuracao", "Selecione uma impressora valida.")
            return

        config.definir_pasta_compartilhada(pasta)
        config.definir_usuario(usuario)
        config.definir_impressora_padrao(impressora)

        self._watcher.iniciar(usuario, pasta)
        self._set_status(STATUS_ATIVO)
        self.btn_iniciar.setEnabled(False)
        self.btn_parar.setEnabled(True)
        self._log(f"Monitoramento iniciado — usuario: {usuario} | impressora: {impressora}")

    def _parar_monitoramento(self):
        self._watcher.parar()
        self._set_status(STATUS_AGUARDANDO)
        self.btn_iniciar.setEnabled(True)
        self.btn_parar.setEnabled(False)
        self._log("Monitoramento parado.")

    # ------------------------------------------------------------------
    # Recepcao de evento
    # ------------------------------------------------------------------
    def _ao_receber_evento(self, evento: dict):
        itens = evento.get("extra", {}).get("itens", [])
        de_display = evento.get("de_display") or evento.get("de") or "?"
        path = evento.get("_path", "")

        if not itens:
            self._log(f"Evento de {de_display} sem itens — ignorado.", erro=True)
            return

        impressora = config.obter_impressora_padrao()
        ok, msg = print_helper.imprimir_itens(itens, impressora=impressora)

        ts = datetime.now().strftime("%H:%M:%S")
        if ok:
            self._log(f"[{ts}]  {de_display} enviou {len(itens)} item(ns) → {msg}")
            self._tray.showMessage(
                "SentPrint — impressao recebida",
                f"{de_display} enviou {len(itens)} item(ns).\n{msg}",
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )
        else:
            self._log(f"[{ts}]  FALHA — {de_display} enviou {len(itens)} item(ns): {msg}", erro=True)
            self._tray.showMessage(
                "SentPrint — FALHA",
                f"Falha ao imprimir: {msg}",
                QSystemTrayIcon.MessageIcon.Warning,
                5000,
            )

        # marca como lida
        if path:
            self._watcher.marcar_lida(path)

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------
    def _log(self, texto: str, erro: bool = False):
        self._log_entries.append((datetime.now().strftime("%d/%m %H:%M:%S"), texto, erro))
        if len(self._log_entries) > MAX_LOG:
            self._log_entries = self._log_entries[-MAX_LOG:]
        item = QListWidgetItem(texto)
        if erro:
            item.setForeground(QColor("#ef4444"))
        else:
            item.setForeground(QColor("#1e293b"))
        self.list_log.addItem(item)
        self.list_log.scrollToBottom()
        # conta impressoes bem sucedidas
        total_ok = sum(1 for _, t, e in self._log_entries if not e and "item(ns)" in t)
        self.lbl_total.setText(f"{total_ok} impressao(es)")

    def _limpar_log(self):
        self._log_entries.clear()
        self.list_log.clear()
        self.lbl_total.setText("0 impressoes")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def _set_status(self, status: str):
        self._status_atual = status
        cor = _STATUS_COLOR.get(status, "#94a3b8")
        self.dot_status.setStyleSheet(f"color: {cor}; font-size: 18px;")
        self.lbl_status.setText(_STATUS_LABEL.get(status, ""))

    def _pulse_status(self):
        """Faz o dot piscar suavemente quando ativo."""
        if self._status_atual != STATUS_ATIVO:
            return
        self._pulse_state = not self._pulse_state
        cor = "#10b981" if self._pulse_state else "#6ee7b7"
        self.dot_status.setStyleSheet(f"color: {cor}; font-size: 18px;")

    # ------------------------------------------------------------------
    # Estilos
    # ------------------------------------------------------------------
    def _aplicar_styles(self):
        self.setStyleSheet("""
            #centralWidget {
                background-color: #f8fafc;
            }
            QWidget {
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
                color: #1e293b;
            }
            #header {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1e1b4b, stop:1 #312e81);
                border: none;
            }
            #appTitle {
                font-size: 18px;
                font-weight: 700;
                color: #ffffff;
                background: transparent;
            }
            #appSub {
                font-size: 11px;
                color: #a5b4fc;
                background: transparent;
            }
            #dotStatus {
                font-size: 18px;
                color: #f59e0b;
                background: transparent;
            }
            #lblStatus {
                font-size: 12px;
                color: #c7d2fe;
                background: transparent;
            }
            #separator {
                background: #e2e8f0;
                border: none;
                max-height: 1px;
            }
            #card {
                background: #ffffff;
                border-radius: 12px;
                border: 1px solid #e2e8f0;
            }
            #cardTitle {
                font-size: 14px;
                font-weight: 700;
                color: #0f172a;
                background: transparent;
            }
            #fieldLabel {
                font-size: 12px;
                color: #64748b;
                font-weight: 600;
                background: transparent;
            }
            QLineEdit {
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 10px;
                background: #ffffff;
                color: #0f172a;
            }
            QLineEdit:focus {
                border-color: #6366f1;
            }
            QComboBox {
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 0 10px;
                background: #ffffff;
                color: #0f172a;
            }
            QComboBox:focus {
                border-color: #6366f1;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            #btnStart {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6366f1, stop:1 #4f46e5);
                color: #ffffff;
                font-weight: 600;
                border-radius: 6px;
                border: none;
                padding: 0 18px;
            }
            #btnStart:hover { background: #4f46e5; }
            #btnStart:disabled { background: #c7d2fe; color: #ffffff; }
            #btnStop {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ef4444, stop:1 #dc2626);
                color: #ffffff;
                font-weight: 600;
                border-radius: 6px;
                border: none;
                padding: 0 18px;
            }
            #btnStop:hover { background: #dc2626; }
            #btnStop:disabled { background: #fca5a5; color: #ffffff; }
            #btnIcon {
                background: #f8fafc;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }
            #btnIcon:hover { background: #e2e8f0; }
            #btnSecondary {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                color: #475569;
                padding: 0 12px;
                font-weight: 500;
            }
            #btnSecondary:hover { background: #f1f5f9; }
            #listLog {
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                background: #ffffff;
                alternate-background-color: #f8fafc;
                font-size: 12px;
                color: #1e293b;
                padding: 4px;
            }
            #lblTotal {
                font-size: 12px;
                color: #6366f1;
                font-weight: 600;
                background: transparent;
            }
            #footer {
                background: #f8fafc;
                border-top: 1px solid #e2e8f0;
            }
            #footerLabel {
                font-size: 11px;
                color: #94a3b8;
                background: transparent;
            }
        """)
