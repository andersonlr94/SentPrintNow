"""
main.py — Entry point do SentPrint.

Modos de execucao:
  python main.py             → modo GUI completo (janela + bandeja)
  python main.py --headless  → modo headless (sem interface, via Task Scheduler)
"""
import sys
import os


def _registrar_hkcu_run():
    """Registra a versao GUI no startup do usuario (HKCU\\Run).
    Executado somente no modo GUI.
    Silencioso — nao exibe mensagens.
    """
    if sys.platform != "win32":
        return
    try:
        import winreg
        chave_run = r"Software\Microsoft\Windows\CurrentVersion\Run"
        if getattr(sys, "frozen", False):
            cmd = f'"{sys.executable}"'
        else:
            script = os.path.abspath(__file__)
            cmd = f'"{sys.executable}" "{script}"'
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, chave_run, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, "SentPrint", 0, winreg.REG_SZ, cmd)
    except Exception:
        pass


def _rodar_headless():
    """Modo headless: QCoreApplication, sem janela, so monitoramento."""
    from headless_worker import rodar_headless
    sys.exit(rodar_headless())


def _rodar_gui():
    """Modo GUI completo com janela e bandeja do sistema."""
    _registrar_hkcu_run()

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from qfluentwidgets import setTheme, Theme
    from main_window import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("SentPrint")
    app.setQuitOnLastWindowClosed(False)   # continua na bandeja ao fechar janela

    setTheme(Theme.LIGHT)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    if "--headless" in sys.argv:
        _rodar_headless()
    else:
        _rodar_gui()
