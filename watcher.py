"""
watcher.py — Observa a inbox do usuario configurado e emite sinal quando chega evento novo.
Mesma logica do Almoxarifado2/core/eventos_watcher.py, porem standalone (sem dependencia do core).
Polling 1500ms + QFileSystemWatcher opcional (SMB geralmente nao dispara o FS watcher).
"""

import json
import os
from PySide6.QtCore import QObject, Signal, QTimer, QFileSystemWatcher

TTL_SEG = 60 * 60 * 2  # 2h — igual ao Almoxarifado2


def _pasta_inbox(base_compartilhada: str, usuario: str) -> str:
    if not base_compartilhada or not usuario:
        return ""
    norm = usuario.strip().lower()
    return os.path.normpath(os.path.join(base_compartilhada, "Almox", "Eventos", "inbox", norm))


def _limpar_antigos(pasta: str, ttl: int = TTL_SEG):
    import time
    if not pasta or not os.path.isdir(pasta):
        return
    agora = time.time()
    for nome in os.listdir(pasta):
        if not nome.endswith(".json"):
            continue
        caminho = os.path.join(pasta, nome)
        try:
            mtime = os.path.getmtime(caminho)
            if agora - mtime > ttl:
                os.remove(caminho)
        except Exception:
            pass


class EventosWatcher(QObject):
    novo_evento = Signal(dict)
    erro = Signal(str)

    def __init__(self, parent=None, intervalo_ms: int = 1500):
        super().__init__(parent)
        self._usuario = ""
        self._pasta = ""
        self._vistos = set()
        self._timer = QTimer(self)
        self._timer.setInterval(intervalo_ms)
        self._timer.timeout.connect(self._poll)
        self._watcher = None

    def iniciar(self, usuario: str, base_compartilhada: str):
        self.parar()
        self._usuario = (usuario or "").strip().lower()
        if not self._usuario or not base_compartilhada:
            return
        self._pasta = _pasta_inbox(base_compartilhada, self._usuario)
        if not self._pasta:
            return
        try:
            os.makedirs(self._pasta, exist_ok=True)
        except Exception:
            pass
        self._vistos.clear()
        # pre-carrega historico existente (nao notifica na inicializacao)
        if os.path.isdir(self._pasta):
            for nome in os.listdir(self._pasta):
                if nome.endswith(".json") and not nome.endswith(".tmp"):
                    path = os.path.join(self._pasta, nome)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        eid = data.get("id") or nome
                        self._vistos.add(eid)
                    except Exception:
                        self._vistos.add(nome)
        # QFileSystemWatcher opcional
        try:
            self._watcher = QFileSystemWatcher(self)
            self._watcher.addPath(self._pasta)
            self._watcher.directoryChanged.connect(lambda _: self._poll())
        except Exception:
            self._watcher = None
        self._timer.start()

    def parar(self):
        try:
            self._timer.stop()
        except Exception:
            pass
        if self._watcher is not None:
            try:
                for p in self._watcher.directories():
                    self._watcher.removePath(p)
            except Exception:
                pass
            self._watcher = None
        self._pasta = ""
        self._usuario = ""

    def _poll(self):
        if not self._usuario or not self._pasta:
            return
        if not os.path.isdir(self._pasta):
            return
        try:
            for nome in os.listdir(self._pasta):
                if not nome.endswith(".json") or nome.endswith(".tmp"):
                    continue
                path = os.path.join(self._pasta, nome)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                eid = data.get("id") or nome
                if eid in self._vistos:
                    continue
                para = (data.get("para") or "").strip().lower()
                if para and para != self._usuario:
                    self._vistos.add(eid)
                    continue
                if data.get("lida"):
                    self._vistos.add(eid)
                    continue
                self._vistos.add(eid)
                data["_path"] = path
                data["_fname"] = nome
                try:
                    self.novo_evento.emit(data)
                except Exception as e:
                    try:
                        self.erro.emit(str(e))
                    except Exception:
                        pass
            # limpeza oportunista
            try:
                _limpar_antigos(self._pasta)
            except Exception:
                pass
        except Exception as e:
            try:
                self.erro.emit(str(e))
            except Exception:
                pass

    def marcar_lida(self, caminho: str):
        """Marca evento como lido no disco (escrita atomica)."""
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["lida"] = True
            from datetime import datetime
            data["lida_em"] = datetime.now().isoformat(timespec="seconds")
            tmp = caminho + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, caminho)
        except Exception:
            pass
