# SentPrint

Aplicativo leve que fica rodando em segundo plano (bandeja do sistema) e imprime automaticamente etiquetas Zebra enviadas pelo **Almoxarifado2**.

---

## Como funciona

```
PC do almoxarifado (Almoxarifado2)
  → usuario seleciona itens em "Separando"
  → clica "Enviar" e escolhe o destinatario
  → evento gravado em: <pasta_compartilhada>/Almox/Eventos/inbox/<usuario>/

PC da manutencao (SentPrint) ← este programa
  → monitora a pasta inbox a cada 1,5s
  → ao detectar novo evento: imprime automaticamente na Zebra configurada
  → mostra notificacao na bandeja e registra no historico
```

---

## Instalacao

```bash
pip install -r requirements.txt
```

## Executar

```bash
python main.py
```

---

## Configuracao (primeira vez)

1. **Pasta compartilhada**: mesma pasta de rede usada pelo Almoxarifado2 (ex: `S:\`)
2. **Usuario**: seu nome de usuario (mesmo cadastrado no Almoxarifado2)
3. **Impressora**: selecione a Zebra local
4. Clique **Iniciar monitoramento**

As configuracoes sao salvas automaticamente e o programa se inicia ja monitorando na proxima vez.

---

## Estrutura do projeto

```
SentPrint/
  main.py          # Entry point
  main_window.py   # Janela principal + bandeja
  watcher.py       # Polling da pasta inbox
  print_helper.py  # Geracao ZPL + envio para impressora Zebra
  config.py        # Configuracoes persistidas (LOCALAPPDATA/SentPrint/)
  requirements.txt
```
