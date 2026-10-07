"""
print_helper.py — Impressao Zebra via ZPL (copiado/adaptado do Almoxarifado2).
"""
import os
import json


def _chave_flexivel(item, *variacoes):
    for chave in variacoes:
        if chave in item:
            valor = item[chave]
            return str(valor) if valor is not None else ""
    return ""


def _buscar_item_por_kardex(kardex: str):
    """Busca item em ItensAlmoxarifado.json pelo Kardex (para pegar Loc novo)."""
    if not kardex:
        return None
    try:
        import config
        base = config.obter_pasta_compartilhada()
        if not base:
            return None
        caminho = os.path.normpath(os.path.join(base, "Almox", "ItensAlmoxarifado", "ItensAlmoxarifado.json"))
        with open(caminho, "r", encoding="utf-8") as f:
            itens = json.load(f)
    except Exception:
        return None

    chaves = ["kardex", "Kardex", "KARDEX"]

    def _extrair(item):
        if not isinstance(item, dict):
            return None
        for k in chaves:
            if str(item.get(k, "")).strip() == kardex:
                return item
        return None

    if isinstance(itens, list):
        for it in itens:
            r = _extrair(it)
            if r:
                return r
    elif isinstance(itens, dict):
        for it in itens.values():
            r = _extrair(it)
            if r:
                return r
    return None


def gerar_zpl_para_itens(itens: list, dpi: int = 203) -> str:
    """Gera payload ZPL para lista de itens."""
    def mm_to_dots(mm, dpi_=203):
        return int(mm * dpi_ / 25.4)

    width = mm_to_dots(100, dpi)
    height = mm_to_dots(40, dpi)
    jobs = []
    for it in itens:
        if not isinstance(it, dict):
            continue
        pedido = str(it.get("pedido", "")).strip()
        kardex = str(it.get("kardex", "")).strip()
        codigo = str(it.get("codigo", "")).strip()
        qtde = str(it.get("qtde", "")).strip()
        requisitante = str(it.get("requisitante", "")).strip()

        loc_override = it.get("loc_override")
        if loc_override is not None:
            loc = str(loc_override).strip()
        else:
            try:
                item_interno = _buscar_item_por_kardex(kardex)
                loc = _chave_flexivel(item_interno, "Loc novo") if item_interno else ""
            except Exception:
                loc = ""
        loc = loc or ""

        zpl = [
            "^XA",
            "^CI28" if it.get("layout") == "estoque" else "",
            "^PON",
            f"^PW{width}",
            f"^LL{height}",
            "^LH0,0",
            f"^FO{mm_to_dots(2, dpi)},{mm_to_dots(2, dpi)}^GB{width - mm_to_dots(4, dpi)},{height - mm_to_dots(4, dpi)},2^FS",
        ]

        if it.get("layout") == "estoque":
            descricao = str(it.get("descricao", "")).strip()
            zpl.extend([
                f"^FO{mm_to_dots(5, dpi)},{mm_to_dots(5, dpi)}^A0N,60,70^FD{codigo}^FS",
                f"^FO{mm_to_dots(5, dpi)},{mm_to_dots(12, dpi)}^A0N,40,50^FD{kardex}^FS",
                f"^FO{mm_to_dots(5, dpi)},{mm_to_dots(20, dpi)}^A0N,25,25^FD{descricao[:40]}^FS",
                f"^FO{mm_to_dots(5, dpi)},{mm_to_dots(30, dpi)}^A0N,50,50^FD {loc}^FS",
            ])
            if qtde:
                zpl.append(f"^FO{mm_to_dots(65, dpi)},{mm_to_dots(30, dpi)}^A0N,50,50^FDQtde: {qtde}^FS")
        else:
            zpl.extend([
                f"^FO{mm_to_dots(5, dpi)},{mm_to_dots(5, dpi)}^A0N,40,40^FD{codigo}^FS",
                f"^FO{mm_to_dots(5, dpi)},{mm_to_dots(12, dpi)}^A0N,30,30^FD{kardex}^FS",
                f"^FO{mm_to_dots(5, dpi)},{mm_to_dots(20, dpi)}^A0N,25,25^FDPed: {pedido}^FS",
                f"^FO{mm_to_dots(50, dpi)},{mm_to_dots(20, dpi)}^A0N,25,25^FDReq: {requisitante}^FS",
                f"^FO{mm_to_dots(5, dpi)},{mm_to_dots(30, dpi)}^A0N,30,30^FDQtde: {qtde}^FS",
                f"^FO{mm_to_dots(50, dpi)},{mm_to_dots(30, dpi)}^A0N,30,30^FDLOC: {loc}^FS",
            ])

        zpl.extend([
            "^PQ1",
            "^XZ",
        ])
        zpl = [linha for linha in zpl if linha]
        jobs.append("\n".join(zpl))
    return "".join(jobs)


def imprimir_itens(itens: list, impressora: str | None = None) -> tuple[bool, str]:
    """
    Envia itens para impressora Zebra via ZPL RAW.
    Retorna (sucesso, mensagem).
    """
    if not itens:
        return False, "Nenhum item para imprimir."

    if not impressora:
        try:
            import config
            impressora = config.obter_impressora_padrao()
        except Exception:
            impressora = ""
    impressora = (impressora or "").strip()
    if not impressora:
        return False, "Nenhuma impressora configurada. Configure em Configuracoes."

    zpl = gerar_zpl_para_itens(itens)
    if not zpl:
        return False, "Falha ao gerar ZPL."

    payload = zpl.encode("utf-8")

    try:
        import win32print
    except ImportError:
        return False, "pywin32 nao encontrado. Instale com: pip install pywin32"

    try:
        hPrinter = win32print.OpenPrinter(impressora)
        try:
            win32print.StartDocPrinter(hPrinter, 1, ("ZPL SentPrint", None, "RAW"))
            try:
                pos = 0
                while pos < len(payload):
                    written = win32print.WritePrinter(hPrinter, payload[pos:])
                    if written <= 0:
                        raise IOError("Falha ao gravar na impressora")
                    pos += written
            finally:
                win32print.EndDocPrinter(hPrinter)
        finally:
            win32print.ClosePrinter(hPrinter)
        return True, f"{len(itens)} etiqueta(s) enviada(s) para {impressora}."
    except Exception as e:
        return False, f"Falha ao enviar para {impressora}: {e}"
