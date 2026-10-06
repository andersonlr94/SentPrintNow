"""
config.py — Configurações persistidas do SentPrint.
Armazena: pasta_compartilhada, usuario, impressora_padrao.
"""
import json
import os
import sys

if sys.platform == "win32":
    _APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SentPrint")
else:
    _APP_DIR = os.path.join(os.path.expanduser("~"), ".sentprint")

os.makedirs(_APP_DIR, exist_ok=True)
ARQUIVO_CONFIG = os.path.join(_APP_DIR, "settings.json")


def _carregar():
    try:
        with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _salvar(dados):
    with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def obter_pasta_compartilhada() -> str:
    dados = _carregar()
    caminho = dados.get("pasta_compartilhada", "")
    if caminho and os.path.isdir(caminho):
        return os.path.normpath(caminho)
    return ""


def definir_pasta_compartilhada(caminho: str):
    dados = _carregar()
    dados["pasta_compartilhada"] = os.path.normpath(caminho)
    _salvar(dados)


def obter_usuario() -> str:
    dados = _carregar()
    return dados.get("usuario", "")


def definir_usuario(usuario: str):
    dados = _carregar()
    dados["usuario"] = usuario.strip().lower()
    _salvar(dados)


def obter_impressora_padrao() -> str:
    dados = _carregar()
    return dados.get("impressora_padrao", "")


def definir_impressora_padrao(nome: str):
    dados = _carregar()
    dados["impressora_padrao"] = nome
    _salvar(dados)


def obter_auto_iniciar() -> bool:
    dados = _carregar()
    return bool(dados.get("auto_iniciar", False))


def definir_auto_iniciar(valor: bool):
    dados = _carregar()
    dados["auto_iniciar"] = valor
    _salvar(dados)
