"""
Fundo fixo SAMS (conta 28200202): relatório, revisão e compensação num fluxo só.

Uso normal: dar duplo clique em "Fundo Fixo.vbs".
  1. Abre a janela do aplicativo (pywebview) e, em segundo plano, extrai a FBL3H e roda a análise.
     Fechar a janela encerra tudo. Sem o pywebview, abre no navegador padrão.
  2. Você revisa, clica em "Montar lote" (salva a_compensar.csv na pasta temp)
     e, na mesma tela, em "Testar na F.13" ou "Compensar".
  3. Ao compensar, cada documento de compensação é salvo em historico_compensacoes.csv.

Nada aparece em terminal: o registro de tudo fica em logs/app.log.

Pré-requisitos (Windows): SAP GUI aberto e logado, scripting habilitado, Python 3.8+ e pywin32.
Na mesma pasta: analisar.py, modelo_revisao.html, relatorio_fbl3h.vbs.

Linha de comando (alternativa):
  py fundo_fixo.py app                      # o mesmo que o .vbs
  py fundo_fixo.py compensar [--efetivo]    # usa a_compensar.csv da pasta temp
  py fundo_fixo.py diagnostico              # grava os campos da seleção múltipla da F.13
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from collections import OrderedDict
from pathlib import Path

# ---------------------------------------------------------------- configuração
PASTA = Path(__file__).resolve().parent
# Valores padrão; podem ser trocados em config.ini (veja config.exemplo.ini)
import configparser
_cfg = configparser.ConfigParser()
_cfg.read(PASTA / "config.ini", encoding="utf-8")
_c = _cfg["fundo_fixo"] if _cfg.has_section("fundo_fixo") else {}
PASTA_RELATORIO = Path(_c.get("pasta_relatorio",
    r"\\brsvp0000009\Groups\dfg\Financeiro\Tesouraria\25 Gestão de Caixa\15. MELHORIAS\FUNDO FIXO"))
ARQ_RELATORIO = PASTA_RELATORIO / "fundo_fixo.txt"
ARQ_LISTA = PASTA_RELATORIO / "a_compensar.csv"
ARQ_HISTORICO = PASTA_RELATORIO / "historico_compensacoes.csv"
VBS_RELATORIO = PASTA / "relatorio_fbl3h.vbs"
PAGINA = PASTA / "revisao_compensacao.html"
MODELO = PASTA / "modelo_revisao.html"
PASTA_LOG = PASTA / "logs"

EMPRESA = _c.get("empresa", "BR21")
CONTA = _c.get("conta", "28200202")
PAUSA = 0.5            # segundos entre passos no SAP
PORTA = 8765
OCIOSO_MAX = 3 * 3600  # encerra sozinho depois de 3 h sem uso

SEM_JANELA = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW


class Falha(Exception):
    """Erro esperado, com mensagem para a pessoa."""


# ---------------------------------------------------------------- registro
_trava_log = threading.Lock()
EVENTOS = []


def log(msg):
    linha = f"[{dt.datetime.now():%d/%m %H:%M:%S}] {msg}"
    with _trava_log:
        EVENTOS.append(linha)
        del EVENTOS[:-80]
        try:
            PASTA_LOG.mkdir(exist_ok=True)
            with open(PASTA_LOG / "app.log", "a", encoding="utf-8") as f:
                f.write(linha + "\n")
        except Exception:
            pass
    try:
        print(linha, flush=True)
    except Exception:
        pass  # pythonw não tem console


# ---------------------------------------------------------------- relatório e análise
def rodar_relatorio():
    if not VBS_RELATORIO.exists():
        raise Falha(f"Não achei o VBS do relatório em {VBS_RELATORIO}.")
    if not PASTA_RELATORIO.exists():
        raise Falha(f"A pasta {PASTA_RELATORIO} não existe ou não está acessível.")
    log("Extraindo a FBL3H...")
    antes = ARQ_RELATORIO.stat().st_mtime if ARQ_RELATORIO.exists() else 0
    r = subprocess.run(["cscript", "//nologo", str(VBS_RELATORIO), str(PASTA_RELATORIO), EMPRESA, CONTA,
                        ARQ_RELATORIO.name], capture_output=True,
                       text=True, creationflags=SEM_JANELA)
    if r.returncode != 0:
        raise Falha("O script da FBL3H falhou. O SAP está aberto e logado? "
                    + (r.stderr or r.stdout).strip()[:300])
    if not ARQ_RELATORIO.exists() or ARQ_RELATORIO.stat().st_mtime <= antes:
        raise Falha(f"O relatório não foi atualizado em {ARQ_RELATORIO}. Confira o SAP.")
    log("FBL3H extraída.")
    return ARQ_RELATORIO


def gerar_pagina(txt):
    sys.path.insert(0, str(PASTA))
    import analisar
    hoje = dt.date.today()
    inicio = hoje.replace(day=1)
    partidas = analisar.ler_exportacao(txt)
    lojas = analisar.analisar(partidas, inicio)
    dados = {
        "arquivo": Path(txt).name, "conta": CONTA, "mes_ref": inicio.isoformat(),
        "gerado_em": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "total_linhas": len(partidas), "lojas": lojas, "demo": False,
    }
    html = MODELO.read_text(encoding="utf-8").replace("/*__DADOS__*/null", json.dumps(dados, ensure_ascii=False))
    PAGINA.write_text(html, encoding="utf-8")
    cont = {}
    for l in lojas:
        cont[l["status"]] = cont.get(l["status"], 0) + 1
    log(f"Análise pronta: {len(partidas)} partidas, {len(lojas)} lojas "
        f"(prontas {cont.get('ok', 0)}, revisar {cont.get('revisar', 0)}, erro {cont.get('erro', 0)}).")


# ---------------------------------------------------------------- lista
def salvar_lista(texto):
    """Valida o CSV vindo da página e grava a_compensar.csv (e uma cópia com data/hora em logs)."""
    linhas = [l.strip() for l in texto.replace("\r", "").split("\n") if l.strip()]
    if not linhas or not linhas[0].lower().startswith("atribuicao;documento"):
        raise Falha("cabeçalho inesperado")
    if len(linhas) < 2:
        raise Falha("lote vazio")
    for l in linhas[1:]:
        p = l.split(";")
        if len(p) < 2 or not p[0].isdigit() or not p[1].isdigit():
            raise Falha(f"linha inválida: {l}")
    conteudo = "\r\n".join(linhas) + "\r\n"
    ARQ_LISTA.write_text(conteudo, encoding="utf-8-sig")
    PASTA_LOG.mkdir(exist_ok=True)
    (PASTA_LOG / f"a_compensar_{dt.datetime.now():%Y%m%d_%H%M%S}.csv").write_text(conteudo, encoding="utf-8-sig")
    log(f"Lote de compensação salvo em {ARQ_LISTA} ({len(linhas) - 1} documentos).")
    return ARQ_LISTA, len(linhas) - 1


def ler_lista(caminho=None):
    caminho = caminho or ARQ_LISTA
    if not Path(caminho).exists():
        raise Falha(f"Não achei {caminho}. Monte o lote de compensação na página de revisão.")
    lojas = OrderedDict()
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        for i, linha in enumerate(csv.reader(f, delimiter=";")):
            if not linha or (i == 0 and linha[0].lower().startswith("atrib")):
                continue
            atrib, doc = linha[0].strip(), linha[1].strip()
            if not (atrib.isdigit() and doc.isdigit()):
                raise Falha(f"Linha {i + 1} inválida no lote: {linha}")
            lojas.setdefault(atrib, [])
            if doc not in lojas[atrib]:
                lojas[atrib].append(doc)
    if not lojas:
        raise Falha("O lote de compensação está vazio.")
    return lojas


def partidas_abertas(txt):
    sys.path.insert(0, str(PASTA))
    from analisar import ler_exportacao
    abertas = {}
    for p in ler_exportacao(txt):
        abertas.setdefault((p["atrib"], p["doc"]), []).append(p)
    return abertas


def par_valido(linhas):
    """Mesmo documento e mesma loja: exatamente 1 débito e 1 crédito, mesmo valor, mesma data DOC, tipo BC."""
    if len(linhas) != 2:
        return f"{len(linhas)} linha(s) em aberto"
    deb = [p for p in linhas if p["valor"] > 0]
    cre = [p for p in linhas if p["valor"] < 0]
    if len(deb) != 1 or len(cre) != 1:
        return "não tem um débito e um crédito"
    if round(deb[0]["valor"] + cre[0]["valor"], 2) != 0:
        return f"débito {deb[0]['valor']} e crédito {cre[0]['valor']} não batem"
    if deb[0]["data_doc"] != cre[0]["data_doc"]:
        return "débito e crédito com datas DOC diferentes"
    if any(p["tipo"] != "BC" for p in linhas):
        return "tipo de documento diferente de BC"
    return None


def validar_com_relatorio(lojas, txt):
    sys.path.insert(0, str(PASTA))
    from analisar import referencia
    abertas = partidas_abertas(txt)
    lojas_do_doc, itens_da_loja = {}, {}
    for (a, d), linhas in abertas.items():
        lojas_do_doc.setdefault(d, set()).add(a)
        itens_da_loja.setdefault(a, []).extend(linhas)
    problemas = []
    for atrib, docs in lojas.items():
        # regra 1: o documento mais antigo da loja é o fundo e nunca é compensado; sem fundo, a loja fica fora
        info = referencia(itens_da_loja.get(atrib, []))
        if not info or not info["valido"]:
            problemas.append(f"{atrib}: loja sem fundo de referência em aberto; nenhum documento dela pode entrar")
            continue
        for d in docs:
            if d == info["doc"]:
                problemas.append(f"{atrib} {d}: é o fundo de referência da loja e nunca é compensado")
                continue
            linhas = abertas.get((atrib, d))
            if not linhas:
                problemas.append(f"{atrib} {d}: não está mais em aberto")
                continue
            # a contrapartida tem que ser da mesma loja; lançamentos de outra loja não contam
            erro = par_valido(linhas)
            if erro:
                problemas.append(f"{atrib} {d}: {erro} nesta loja")
                continue
            outras = sorted(lojas_do_doc.get(d, set()) - {atrib})
            if outras:
                problemas.append(f"{atrib} {d}: o mesmo nº de documento tem lançamento na loja "
                                 f"{', '.join(outras)}; a F.13 incluiria esse lançamento")
    return problemas


def ainda_abertos(lojas, txt):
    abertas = partidas_abertas(txt)
    return [f"{atrib} {d}" for atrib, docs in lojas.items() for d in docs if (atrib, d) in abertas]


# ---------------------------------------------------------------- SAP
def sessao_sap():
    import win32com.client
    try:
        gui = win32com.client.GetObject("SAPGUI")
        return gui.GetScriptingEngine.Children(0).Children(0)
    except Exception:
        raise Falha("Não encontrei uma sessão do SAP GUI aberta. Abra e faça login antes.")


def existe(s, id_):
    try:
        s.findById(id_)
        return True
    except Exception:
        return False


def barra(s):
    sb = s.findById("wnd[0]/sbar")
    return sb.MessageType, sb.Text


def textos_da_lista(s):
    """Texto da lista de saída da F.13 (usado no log e para achar o doc. de compensação)."""
    out = []
    try:
        usr = s.findById("wnd[0]/usr")
        for i in range(usr.Children.Count):
            t = (getattr(usr.Children.ElementAt(i), "Text", "") or "").strip()
            if t:
                out.append(t)
    except Exception:
        pass
    return " | ".join(out)


def docs_compensacao(texto, docs_entrada):
    """Números de documento na saída da F.13 que não são os documentos compensados."""
    entrada = {d.lstrip("0") for d in docs_entrada}
    achados = []
    for n in re.findall(r"(?<!\d)\d{9,10}(?!\d)", texto):
        n2 = n.lstrip("0")
        if n2 in entrada or n2 == CONTA.lstrip("0") or n2 in achados:
            continue
        achados.append(n2)
    return achados


TABELA_SELECAO = ("wnd[1]/usr/tabsTAB_STRIP/tabpSIVA/ssubSCREEN_HEADER:SAPLALDB:3010"
                  "/tblSAPLALDBSINGLE")
CELULA = TABELA_SELECAO + "/txtRSCSEL_255-SLOW_I[1,{}]"


def _linhas_visiveis(s):
    try:
        return max(1, int(s.findById(TABELA_SELECAO).VisibleRowCount))
    except Exception:
        return 8


def _rolar(s, pos):
    s.findById(TABELA_SELECAO).verticalScrollbar.position = pos
    time.sleep(0.2)


def _posicao(s):
    return int(s.findById(TABELA_SELECAO).verticalScrollbar.position)


def _ir_para(s, alvo):
    """Rola a seleção até a linha `alvo` (contando do início) ficar visível e devolve o índice dela na tela.

    O SAP pode parar a rolagem antes do pedido (com 8 documentos, a posição 8 vira 7), então a posição
    real é sempre relida. Se a linha não ficar visível nem depois de um Enter, para com erro."""
    vis = _linhas_visiveis(s)
    for tentativa in range(3):
        pos = _posicao(s)
        if pos <= alvo < pos + vis:
            return alvo - pos
        try:
            _rolar(s, max(0, alvo - vis + 1))  # deixa o alvo na última linha visível
        except Exception:
            pass
        pos = _posicao(s)
        if pos <= alvo < pos + vis:
            return alvo - pos
        s.findById("wnd[1]").sendVKey(0)  # Enter: o SAP grava as linhas digitadas e libera mais rolagem
        time.sleep(0.3)
    raise RuntimeError(f"não consegui chegar à linha {alvo + 1} da seleção múltipla; nada foi executado")


def digitar_documentos(s, docs):
    for i, doc in enumerate(docs):
        s.findById(CELULA.format(_ir_para(s, i))).text = doc
    s.findById("wnd[1]").sendVKey(0)
    time.sleep(0.3)


def ler_selecao(s):
    _rolar(s, 0)
    lidos = []
    while len(lidos) < 5000:
        try:
            v = s.findById(CELULA.format(_ir_para(s, len(lidos)))).text.strip()
        except RuntimeError:
            raise
        except Exception:
            v = ""
        if not v:
            break
        lidos.append(v.lstrip("0"))
    _rolar(s, 0)
    return lidos


def conferir_selecao(s, docs):
    lidos = ler_selecao(s)
    if sorted(lidos) != sorted(d.lstrip("0") for d in docs):
        sobra = sorted(set(lidos) - {d.lstrip("0") for d in docs})
        falta = sorted({d.lstrip("0") for d in docs} - set(lidos))
        raise RuntimeError(f"seleção não bate (esperados {len(docs)}, lidos {len(lidos)}; "
                           f"faltam {falta[:3]}, sobram {sobra[:3]})")


def fechar_janelas(s):
    for _ in range(5):
        if not existe(s, "wnd[1]"):
            return
        try:
            s.findById("wnd[1]").close()
        except Exception:
            s.findById("wnd[1]").sendVKey(12)
        time.sleep(0.3)


def f13_loja(s, docs, teste):
    """Roda a F.13 para os documentos de uma loja. Devolve (status, mensagem, docs_compensacao)."""
    fechar_janelas(s)
    s.findById("wnd[0]/tbar[0]/okcd").text = "/nF.13"
    s.findById("wnd[0]").sendVKey(0)
    time.sleep(PAUSA)

    s.findById("wnd[0]/usr/chkX_SAKNR").selected = True
    s.findById("wnd[0]/usr/ctxtBUKRX-LOW").text = EMPRESA
    s.findById("wnd[0]/usr/txtGJAHX-LOW").text = str(dt.date.today().year)
    s.findById("wnd[0]/usr/ctxtKONTS-LOW").text = CONTA

    s.findById("wnd[0]/usr/btn%_DOCNR_%_APP_%-VALU_PUSH").press()
    time.sleep(PAUSA)
    if ler_selecao(s):
        raise RuntimeError("a seleção múltipla já veio preenchida; nada foi executado")
    digitar_documentos(s, docs)
    conferir_selecao(s, docs)
    s.findById("wnd[1]/tbar[0]/btn[8]").press()
    time.sleep(PAUSA)

    s.findById("wnd[0]/usr/chkX_TESTL").selected = teste
    s.findById("wnd[0]/tbar[1]/btn[8]").press()
    time.sleep(PAUSA)

    for _ in range(4):  # aviso FG013 na execução efetiva
        if existe(s, "wnd[1]"):
            s.findById("wnd[1]/tbar[0]/btn[0]").press()
        elif existe(s, "wnd[0]/usr/chkX_TESTL"):
            tipo, txt = barra(s)
            if tipo in ("E", "A"):
                return "erro", txt, []
            s.findById("wnd[0]").sendVKey(0 if tipo == "W" else 8)
        else:
            break
        time.sleep(PAUSA)

    if existe(s, "wnd[0]/usr/chkX_TESTL"):
        return "erro", "A F.13 não saiu da tela de seleção: " + barra(s)[1], []
    tipo, txt = barra(s)
    if tipo in ("E", "A"):
        return "erro", txt, []
    saida = textos_da_lista(s)
    comp = [] if teste else docs_compensacao(txt + " " + saida, docs)
    return "ok", ((txt + " | ") if txt else "") + saida[:2000], comp


def registrar_historico(atrib, docs, status, comp, msg):
    novo = not ARQ_HISTORICO.exists()
    with open(ARQ_HISTORICO, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["data_hora", "loja", "documentos", "doc_compensacao", "status", "mensagem_sap"])
        w.writerow([f"{dt.datetime.now():%d/%m/%Y %H:%M:%S}", atrib, " ".join(docs),
                    " ".join(comp), status, msg[:500]])


# ---------------------------------------------------------------- compensação
def executar_compensacao(efetivo, por_documento=False, progresso=None):
    """Valida a_compensar.csv contra a FBL3H atual, roda a F.13 loja por loja e confere o resultado."""
    import pythoncom
    pythoncom.CoInitialize()
    try:
        modo = "EFETIVA" if efetivo else "TESTE"
        lojas = ler_lista()
        n_docs = sum(len(d) for d in lojas.values())
        log(f"Compensação {modo}: {len(lojas)} lojas, {n_docs} documentos.")

        txt = rodar_relatorio()
        problemas = validar_com_relatorio(lojas, txt)
        if problemas:
            raise Falha("O lote não bate com a FBL3H atual. Nada foi executado: " + "; ".join(problemas[:10]))
        log("Lote conferido: cada documento tem 1 débito e 1 crédito BC, mesmo valor e mesma data DOC.")

        execucoes = (OrderedDict((f"{a} {d}", [d]) for a, ds in lojas.items() for d in ds)
                     if por_documento else lojas)
        if progresso:
            progresso("inicio", [{"loja": k, "docs": v} for k, v in execucoes.items()])

        s = sessao_sap()
        PASTA_LOG.mkdir(exist_ok=True)
        log_path = PASTA_LOG / f"f13_{modo.lower()}_{dt.datetime.now():%Y%m%d_%H%M%S}.csv"
        resultados = []
        with open(log_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["data_hora", "modo", "loja", "documentos", "status", "doc_compensacao", "mensagem_sap"])
            for i, (rotulo, docs) in enumerate(execucoes.items()):
                try:
                    status, msg, comp = f13_loja(s, docs, teste=not efetivo)
                except Exception as e:
                    status, msg, comp = "erro", f"Falha no script: {e}", []
                    try:
                        fechar_janelas(s)
                    except Exception:
                        pass
                log(f"{rotulo}: {status}" + (f" | doc. compensação {' '.join(comp)}" if comp else "")
                    + (f" | {msg[:200]}" if status != "ok" else ""))
                w.writerow([f"{dt.datetime.now():%d/%m/%Y %H:%M:%S}", modo, rotulo, " ".join(docs),
                            status, " ".join(comp), msg])
                f.flush()
                if efetivo:
                    registrar_historico(rotulo, docs, status, comp, msg)
                r = {"loja": rotulo, "docs": docs, "status": status, "doc_comp": comp,
                     "msg": msg[:300] if status != "ok" else ""}
                resultados.append(r)
                if progresso:
                    progresso("loja", r)

        try:
            s.findById("wnd[0]/tbar[0]/okcd").text = "/n"
            s.findById("wnd[0]").sendVKey(0)
        except Exception:
            pass

        conclusao = f"Teste concluído. Log em {log_path.name}."
        if efetivo:
            txt = rodar_relatorio()
            abertos = ainda_abertos(lojas, txt)
            gerar_pagina(txt)
            if abertos:
                conclusao = (f"{len(abertos)} documento(s) continuam em aberto: " + ", ".join(abertos[:10]))
            else:
                conclusao = f"Tudo certo: os {n_docs} documentos saíram das partidas em aberto."
            log(conclusao)
        else:
            gerar_pagina(txt)
        return resultados, conclusao
    finally:
        pythoncom.CoUninitialize()


# ---------------------------------------------------------------- aplicativo (servidor local)
ESTADO = {"fase": "iniciando", "mensagem": "", "job": None}
_trava = threading.Lock()
_ultimo_uso = [time.time()]

CARREGANDO = """<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Compensação Fundo Fixo SAMS</title>
<style>
:root{--bg:#f3f5f4;--surface:#fff;--ink:#17201d;--muted:#56645f;--line:#d6dedb;--accent:#0f5c55;--crit:#a3261b}
@media (prefers-color-scheme:dark){:root{--bg:#0f1513;--surface:#171f1c;--ink:#e4ece9;--muted:#9aa9a3;--line:#29342f;--accent:#5cc2b6;--crit:#f28b80;color-scheme:dark}}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:560px;margin:12vh auto 0;padding:0 16px}
h1{font-size:1.4rem;margin:0 0 6px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:18px;margin-top:16px}
.spin{width:22px;height:22px;border:3px solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:g 1s linear infinite;display:inline-block;vertical-align:middle;margin-right:10px}
@keyframes g{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.spin{animation:none}}
#msg{font-weight:600}
.err #msg{color:var(--crit)} .err .spin{display:none}
ul{margin:12px 0 0;padding:0;list-style:none;font:13px/1.5 ui-monospace,Consolas,monospace;color:var(--muted);max-height:40vh;overflow:auto}
.dica{color:var(--muted);font-size:.9rem}
button{margin-top:14px;min-height:44px;padding:0 16px;border-radius:8px;border:1px solid var(--accent);background:var(--accent);color:#fff;font:inherit;font-weight:600;cursor:pointer}
</style>
<main>
<h1>Compensação Fundo Fixo SAMS</h1>
<p class="dica">Se o SAP perguntar se um script pode acessar o SAP GUI, clique em OK.</p>
<div class="card" id="card"><span class="spin" aria-hidden="true"></span><span id="msg" role="status">Preparando...</span>
<ul id="ev"></ul><button id="tentar" hidden type="button">Tentar de novo</button></div>
</main>
<script>
async function tick(){
  try{
    const r = await fetch("/status",{cache:"no-store"}); const j = await r.json();
    document.getElementById("msg").textContent = j.mensagem || "Preparando...";
    document.getElementById("ev").innerHTML = (j.eventos||[]).slice(-8).map(e=>"<li>"+e.replace(/</g,"&lt;")+"</li>").join("");
    if(j.fase==="pronto"){ location.reload(); return; }
    const erro = j.fase==="erro";
    document.getElementById("card").classList.toggle("err", erro);
    document.getElementById("tentar").hidden = !erro;
    if(erro) return;
  }catch(e){ document.getElementById("msg").textContent = "Sem resposta do aplicativo. Abra o Fundo Fixo de novo."; return; }
  setTimeout(tick, 1000);
}
document.getElementById("tentar").addEventListener("click", async () => {
  await fetch("/atualizar",{method:"POST"}); document.getElementById("tentar").hidden = true;
  document.getElementById("card").classList.remove("err"); tick();
});
tick();
</script></html>"""


def _job_ativo():
    j = ESTADO["job"]
    return j is not None and j.get("ativo")


def tarefa_preparar():
    import pythoncom
    pythoncom.CoInitialize()
    try:
        with _trava:
            ESTADO.update(fase="preparando", mensagem="Extraindo a FBL3H no SAP...")
        txt = rodar_relatorio()
        with _trava:
            ESTADO["mensagem"] = "Analisando as partidas..."
        gerar_pagina(txt)
        with _trava:
            ESTADO.update(fase="pronto", mensagem="Pronto.")
    except Falha as e:
        log(f"Erro: {e}")
        with _trava:
            ESTADO.update(fase="erro", mensagem=str(e))
    except Exception as e:
        log("Erro inesperado: " + traceback.format_exc())
        with _trava:
            ESTADO.update(fase="erro", mensagem=f"Erro inesperado: {e}")
    finally:
        pythoncom.CoUninitialize()


def tarefa_compensar(efetivo, por_documento):
    def progresso(evento, dados):
        with _trava:
            j = ESTADO["job"]
            if evento == "inicio":
                j["total"] = len(dados)
                j["lojas"] = [{"loja": d["loja"], "docs": d["docs"], "status": "pendente", "doc_comp": [], "msg": ""}
                              for d in dados]
                j["mensagem"] = "Rodando a F.13..."
            else:
                j["feitos"] += 1
                for l in j["lojas"]:
                    if l["loja"] == dados["loja"]:
                        l.update(dados)
                pend = next((l for l in j["lojas"] if l["status"] == "pendente"), None)
                j["mensagem"] = f"Rodando a F.13: loja {pend['loja']}..." if pend else "Conferindo o resultado na FBL3H..."

    try:
        _, conclusao = executar_compensacao(efetivo, por_documento, progresso)
        with _trava:
            ESTADO["job"].update(ativo=False, concluido=True, mensagem=conclusao)
    except Falha as e:
        log(f"Erro: {e}")
        with _trava:
            ESTADO["job"].update(ativo=False, concluido=True, erro=str(e), mensagem=str(e))
    except Exception as e:
        log("Erro inesperado: " + traceback.format_exc())
        with _trava:
            ESTADO["job"].update(ativo=False, concluido=True, erro=f"Erro inesperado: {e}", mensagem=f"Erro inesperado: {e}")


def iniciar_servidor():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import urllib.request

    class Handler(BaseHTTPRequestHandler):
        def _enviar(self, codigo, corpo, tipo):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, codigo, dados):
            self._enviar(codigo, json.dumps(dados, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _corpo(self):
            n = int(self.headers.get("Content-Length", 0))
            return self.rfile.read(n).decode("utf-8-sig") if n else ""

        def do_GET(self):
            _ultimo_uso[0] = time.time()
            rota = self.path.split("?")[0]
            if rota in ("/", "/index.html"):
                with _trava:
                    pronto = ESTADO["fase"] == "pronto" and PAGINA.exists()
                corpo = PAGINA.read_bytes() if pronto else CARREGANDO.encode("utf-8")
                self._enviar(200, corpo, "text/html; charset=utf-8")
            elif rota == "/historico":
                linhas = []
                try:
                    if ARQ_HISTORICO.exists():
                        with open(ARQ_HISTORICO, encoding="utf-8-sig", newline="") as f:
                            for r in csv.DictReader(f, delimiter=";"):
                                linhas.append({k: (v or "")[:400] for k, v in r.items() if k})
                    self._json(200, {"ok": True, "arquivo": str(ARQ_HISTORICO), "linhas": linhas[::-1]})
                except Exception as e:
                    self._json(500, {"ok": False, "erro": str(e)})
            elif rota == "/status":
                with _trava:
                    dados = json.loads(json.dumps(ESTADO))
                dados["eventos"] = EVENTOS[-20:]
                self._json(200, dados)
            else:
                self.send_error(404)

        def do_POST(self):
            _ultimo_uso[0] = time.time()
            rota = self.path.split("?")[0]
            if rota == "/salvar-lista":
                try:
                    destino, qtd = salvar_lista(self._corpo())
                    self._json(200, {"ok": True, "caminho": str(destino), "documentos": qtd})
                except Exception as e:
                    log(f"Lote recusado: {e}")
                    self._json(400, {"ok": False, "erro": str(e)})
            elif rota == "/compensar":
                try:
                    pedido = json.loads(self._corpo() or "{}")
                except Exception:
                    pedido = {}
                efetivo = pedido.get("modo") == "efetivo"
                if efetivo and pedido.get("confirmacao") != "COMPENSAR":
                    self._json(400, {"ok": False, "erro": "Confirmação ausente."})
                    return
                with _trava:
                    if _job_ativo() or ESTADO["fase"] == "preparando":
                        self._json(409, {"ok": False, "erro": "Já existe uma tarefa em andamento."})
                        return
                    ESTADO["job"] = {"tipo": "efetivo" if efetivo else "teste", "ativo": True, "concluido": False,
                                     "total": 0, "feitos": 0, "lojas": [], "erro": "",
                                     "mensagem": "Conferindo o lote com a FBL3H atual..."}
                threading.Thread(target=tarefa_compensar,
                                 args=(efetivo, bool(pedido.get("por_documento"))), daemon=True).start()
                self._json(200, {"ok": True})
            elif rota == "/atualizar":
                with _trava:
                    if _job_ativo() or ESTADO["fase"] == "preparando":
                        self._json(409, {"ok": False, "erro": "Já existe uma tarefa em andamento."})
                        return
                    ESTADO.update(fase="preparando", mensagem="Extraindo a FBL3H no SAP...", job=None)
                threading.Thread(target=tarefa_preparar, daemon=True).start()
                self._json(200, {"ok": True})
            elif rota == "/encerrar":
                self._json(200, {"ok": True})
                log("Encerrado a pedido (outra instância foi aberta).")
                threading.Thread(target=encerrar_tudo, args=(self.server,), daemon=True).start()
            else:
                self.send_error(404)

        def log_message(self, *a):
            pass

    # se já houver uma instância aberta, pede para ela encerrar
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    except OSError:
        try:
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORTA}/encerrar", method="POST"), timeout=3)
            time.sleep(1.5)
            srv = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
        except Exception:
            srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    return srv


JANELA = [None]


def encerrar_tudo(srv):
    """Fecha a janela do aplicativo (se houver) e o servidor local."""
    try:
        if JANELA[0] is not None:
            JANELA[0].destroy()
    except Exception:
        pass
    try:
        srv.shutdown()
    except Exception:
        pass


def abrir_janela(url, srv):
    """Abre a página numa janela própria (pywebview). Devolve False se o pywebview não estiver disponível."""
    try:
        import webview
    except ImportError:
        log("pywebview não encontrado; abrindo no navegador padrão.")
        return False

    janela = webview.create_window("Compensação Fundo Fixo SAMS", url, width=1180, height=860,
                                   min_size=(420, 600), text_select=True)
    JANELA[0] = janela

    def ao_fechar():
        if _job_ativo():
            # não deixa fechar no meio da F.13
            def avisar():
                try:
                    janela.evaluate_js("alert('A compensação ainda está rodando no SAP. Espere terminar para fechar.')")
                except Exception:
                    pass
            threading.Thread(target=avisar, daemon=True).start()  # fora da thread da janela
            return False
        return True

    def fechou():
        log("Janela fechada. Encerrando.")
        threading.Thread(target=srv.shutdown, daemon=True).start()

    janela.events.closing += ao_fechar
    janela.events.closed += fechou

    dados = PASTA / "dados_janela"  # guarda tema e seleções entre um uso e outro
    try:
        webview.start(private_mode=False, storage_path=str(dados))
    except TypeError:
        webview.start()
    return True


def app(args=None):
    srv = iniciar_servidor()
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    log(f"Aplicativo iniciado em {url}")
    with _trava:
        ESTADO.update(fase="preparando", mensagem="Extraindo a FBL3H no SAP...")
    threading.Thread(target=tarefa_preparar, daemon=True).start()
    servidor = threading.Thread(target=srv.serve_forever, daemon=True)
    servidor.start()

    try:
        if abrir_janela(url, srv):  # bloqueia até a janela fechar
            return
    except Exception:
        log("Falha ao abrir a janela; usando o navegador. " + traceback.format_exc())

    # alternativa: navegador padrão do Windows, com encerramento por inatividade
    def vigia():
        while True:
            time.sleep(60)
            if time.time() - _ultimo_uso[0] > OCIOSO_MAX and not _job_ativo():
                log("Encerrado por inatividade.")
                srv.shutdown()
                return
    threading.Thread(target=vigia, daemon=True).start()
    try:
        os.startfile(url)
    except Exception:
        import webbrowser
        webbrowser.open(url)
    servidor.join()
    srv.server_close()


# ---------------------------------------------------------------- linha de comando
def compensar_cli(args):
    try:
        if args.efetivo:
            lojas = ler_lista()
            n = sum(len(d) for d in lojas.values())
            if input(f"Compensar {n} documentos em {len(lojas)} lojas? Digite COMPENSAR: ").strip().upper() != "COMPENSAR":
                print("Cancelado. Nada foi lançado.")
                return
        _, conclusao = executar_compensacao(args.efetivo, args.por_documento)
        print("\n" + conclusao)
    except Falha as e:
        print(f"\n{e}")
        sys.exit(1)


def diagnostico(args):
    s = sessao_sap()
    s.findById("wnd[0]/tbar[0]/okcd").text = "/nF.13"
    s.findById("wnd[0]").sendVKey(0)
    time.sleep(PAUSA)
    s.findById("wnd[0]/usr/btn%_DOCNR_%_APP_%-VALU_PUSH").press()
    time.sleep(PAUSA)
    linhas = []

    def andar(obj, nivel=0):
        try:
            txt = getattr(obj, "Text", "")
        except Exception:
            txt = ""
        linhas.append(f"{'  ' * nivel}{obj.Type:<22} {obj.Id}  [{txt}]")
        try:
            for i in range(obj.Children.Count):
                andar(obj.Children.ElementAt(i), nivel + 1)
        except Exception:
            pass

    andar(s.findById("wnd[1]"))
    PASTA_LOG.mkdir(exist_ok=True)
    destino = PASTA_LOG / "diagnostico_selecao_multipla.txt"
    destino.write_text("\n".join(linhas), encoding="utf-8")
    print(f"Diagnóstico salvo em {destino}.")
    os.startfile(destino)


def main():
    ap = argparse.ArgumentParser(description="Fundo fixo SAMS: revisão e compensação")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("app", help="abre o aplicativo no navegador (padrão)")
    sub.add_parser("revisar", help="o mesmo que app")
    sub.add_parser("diagnostico", help="grava os campos da seleção múltipla da F.13")
    c = sub.add_parser("compensar", help="roda a F.13 com a_compensar.csv da pasta temp")
    c.add_argument("--efetivo", action="store_true", help="lança a compensação (sem isso, roda em teste)")
    c.add_argument("--por-documento", action="store_true", help="uma execução da F.13 por documento")
    a = ap.parse_args()
    cmd = a.cmd or "app"
    try:
        {"app": app, "revisar": app, "compensar": compensar_cli, "diagnostico": diagnostico}[cmd](a)
    except Exception:
        log("Erro fatal: " + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
