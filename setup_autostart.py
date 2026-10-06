"""
setup_autostart.py — Configura inicializacao automatica do SentPrint.

Execute UMA VEZ como Administrador para registrar:
  1. Task Scheduler (roda headless antes do login)
  2. HKCU\Run (roda com interface apos o login)

Uso: python setup_autostart.py
"""
import ctypes
import getpass
import os
import subprocess
import sys
import winreg


TASK_NAME = "SentPrint Headless"

# ── Helpers ──────────────────────────────────────────────────────────

def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _cmd_headless() -> str:
    """Monta o comando que o Task Scheduler vai executar."""
    python = sys.executable
    script = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"))
    return f'"{python}" "{script}" --headless'


def _cmd_gui() -> str:
    """Monta o comando que o HKCU\Run vai executar."""
    python = sys.executable
    script = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"))
    return f'"{python}" "{script}"'


# ── 1. Task Scheduler ────────────────────────────────────────────────

def criar_tarefa_scheduler(usuario: str, senha: str) -> bool:
    """
    Cria tarefa no Task Scheduler que roda ao iniciar o sistema,
    mesmo sem nenhum usuario logado.
    Requer privilegios de Administrador.
    """
    cmd = _cmd_headless()
    result = subprocess.run(
        [
            "schtasks", "/Create",
            "/TN", TASK_NAME,
            "/TR", cmd,
            "/SC", "ONSTART",       # ao iniciar o sistema
            "/RU", usuario,         # roda como este usuario (acessa rede)
            "/RP", senha,           # senha armazenada de forma segura pelo SO
            "/RL", "HIGHEST",       # privilegio mais alto disponivel
            "/DELAY", "0000:30",    # aguarda 30s para rede estabilizar
            "/F",                   # sobrescreve se ja existir
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("  [OK] Tarefa criada no Task Scheduler.")
        return True
    else:
        print(f"  [ERRO] {result.stderr.strip() or result.stdout.strip()}")
        return False


# ── 2. HKCU\Run ──────────────────────────────────────────────────────

def registrar_hkcu_run() -> bool:
    """Registra a versao GUI no startup do usuario (HKCU\\Run)."""
    try:
        chave = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "SentPrint", 0, winreg.REG_SZ, _cmd_gui())
        print("  [OK] HKCU\\Run registrado (GUI apos login).")
        return True
    except Exception as e:
        print(f"  [ERRO] {e}")
        return False


# ── Remover ──────────────────────────────────────────────────────────

def remover_tarefa_scheduler():
    subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
    )
    print("  [OK] Tarefa removida do Task Scheduler.")


def remover_hkcu_run():
    try:
        chave = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, "SentPrint")
        print("  [OK] HKCU\\Run removido.")
    except FileNotFoundError:
        print("  [OK] Entrada nao existia.")
    except Exception as e:
        print(f"  [ERRO] {e}")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 56)
    print("   SentPrint — Configuracao de Inicializacao Automatica")
    print("=" * 56)
    print()

    if not _is_admin():
        print("ATENCAO: Execute este script como Administrador.")
        print("(Botao direito em setup_autostart.py -> Abrir com Python -> como Admin)")
        print()
        input("Pressione Enter para sair...")
        sys.exit(1)

    print("Escolha uma opcao:")
    print("  [1] Instalar inicializacao automatica")
    print("  [2] Remover inicializacao automatica")
    print()
    opcao = input("Opcao (1/2): ").strip()

    if opcao == "2":
        print()
        print("Removendo...")
        remover_tarefa_scheduler()
        remover_hkcu_run()
        print()
        print("Inicializacao automatica removida com sucesso.")
        input("\nPressione Enter para sair...")
        return

    if opcao != "1":
        print("Opcao invalida.")
        input("\nPressione Enter para sair...")
        return

    print()
    print("O Task Scheduler precisara da sua senha do Windows para rodar")
    print("o SentPrint antes do login (acessando a pasta de rede).")
    print()

    # Detecta usuario atual
    domain   = os.environ.get("USERDOMAIN", "")
    username = os.environ.get("USERNAME", getpass.getuser())
    full_user = f"{domain}\\{username}" if domain and domain != username else username

    print(f"Usuario detectado: {full_user}")
    confirma = input("Usar este usuario? (S/n): ").strip().lower()
    if confirma == "n":
        full_user = input("Digite o usuario (DOMINIO\\usuario ou usuario): ").strip()

    senha = getpass.getpass("Senha do Windows: ")

    print()
    print("Registrando...")

    ok_task = criar_tarefa_scheduler(full_user, senha)
    ok_run  = registrar_hkcu_run()

    print()
    if ok_task and ok_run:
        print("Configuracao concluida com sucesso!")
        print()
        print("  Sem login  → Task Scheduler sobe o SentPrint em modo headless")
        print("               (so imprime, sem interface, log em %LOCALAPPDATA%\\SentPrint\\headless.log)")
        print("  Apos login → HKCU\\Run sobe o SentPrint com interface completa")
        print("               (headless encerra automaticamente, GUI assume)")
        print()
        print("IMPORTANTE: A pasta de rede e a impressora devem estar configuradas")
        print("no SentPrint antes de reiniciar o PC.")
    else:
        print("Alguns itens falharam. Verifique os erros acima.")

    print()
    input("Pressione Enter para sair...")


if __name__ == "__main__":
    main()
