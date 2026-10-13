"""
Análise da conta 28200202 (fundo fixo SAMS) a partir da exportação da FBL3H.

Uso:
    python analisar.py exportacao.txt                 # mês de referência = mês atual
    python analisar.py exportacao.txt --mes 2026-10   # força o mês de referência

Gera:
    revisao_compensacao.html  -> página para o analista revisar e selecionar os documentos
    analise.json              -> mesmo resultado em formato de dados (para o script de compensação)

Regras (reunião de 08/10/2026):
  - Ignora a partida inicial (SE/AB) e tudo com data DOC anterior ao mês de referência.
  - No mês: só tipo BC entra na compensação. Cada nº de documento precisa ter
    exatamente um débito (40) e um crédito (50) que somam zero.
  - Confere o valor do par com o fundo de referência da loja (partidas SE/AB).
  - Aponta duas datas DOC iguais na mesma loja e dias sem lançamento.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

COLS = {
    "Empresa": "empresa",
    "Data do documento": "data_doc",
    "Data de lançamento": "data_lanc",
    "Nº documento": "doc",
    "Tipo de documento": "tipo",
    "Valor em moeda da empresa": "valor",
    "Chave de lançamento": "chave",
    "Atribuição": "atrib",
    "Texto": "texto",
}


# Nomes técnicos do SAP, usados quando o cabeçalho vem como "Data doc. (BLDAT)"
TECNICOS = {
    "BUKRS": "empresa", "BLDAT": "data_doc", "BUDAT": "data_lanc", "BELNR": "doc",
    "BLART": "tipo", "CURRVAL_10": "valor", "DMBTR": "valor", "BSCHL": "chave",
    "ZUONR": "atrib", "SGTXT": "texto",
}


def campo(cab):
    m = re.search(r"\(([A-Z0-9_]+)\)\s*$", cab)
    if m and m.group(1) in TECNICOS:
        return TECNICOS[m.group(1)]
    return COLS.get(cab)


def split_line(line):
    if "\t" in line:
        return [p.strip() for p in line.split("\t")]
    return [p.strip() for p in re.split(r" {8}", line)]


def to_num(s):
    return round(float(s.replace(".", "").replace(",", ".")), 2)


def to_date(s):
    return datetime.strptime(s.replace(".", "/"), "%d/%m/%Y").date()


def ler_exportacao(caminho):
    raw = Path(caminho).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    linhas = [l for l in texto.splitlines() if l.strip()]
    cab = split_line(linhas[0])
    idx = {}
    for i, c in enumerate(cab):
        nome = campo(c)
        if nome and nome not in idx:
            idx[nome] = i
    faltando = set(COLS.values()) - set(idx)
    if faltando:
        sys.exit(f"Colunas não encontradas na exportação: {', '.join(sorted(faltando))}")
    partidas = []
    for l in linhas[1:]:
        p = split_line(l)
        p += [""] * (len(cab) - len(p))
        if not p[idx["empresa"]]:  # linha de subtotal do SAP
            continue
        partidas.append({
            "data_doc": to_date(p[idx["data_doc"]]),
            "data_lanc": to_date(p[idx["data_lanc"]]),
            "doc": p[idx["doc"]],
            "tipo": p[idx["tipo"]],
            "valor": to_num(p[idx["valor"]]),
            "chave": p[idx["chave"]],
            "atrib": p[idx["atrib"]],
            "texto": p[idx["texto"]],
        })
    return partidas


def brl(v):
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if v < 0 else "") + s


def analisar(partidas, inicio_mes):
    por_loja = defaultdict(list)
    for p in partidas:
        por_loja[p["atrib"]].append(p)

    # um mesmo nº de documento não pode ter lançamentos em lojas (atribuições) diferentes
    lojas_do_doc = defaultdict(set)
    for p in partidas:
        lojas_do_doc[p["doc"]].add(p["atrib"])

    lojas = []
    for atrib in sorted(por_loja):
        itens = por_loja[atrib]
        ref = [p for p in itens if p["tipo"] in ("SE", "AB")]
        fundo = round(sum(p["valor"] for p in ref), 2) if ref else None
        mes = [p for p in itens if p["data_doc"] >= inicio_mes and p["tipo"] not in ("SE", "AB")]
        antigas = [p for p in itens if p not in mes and p not in ref]

        erros, revisar, avisos = [], [], []
        docs = []

        bc = defaultdict(list)
        for p in mes:
            if p["tipo"] == "BC":
                bc[p["doc"]].append(p)
            else:
                revisar.append(f"Lançamento {p['tipo']} {p['doc']} ({p['data_doc']:%d/%m}), {brl(p['valor'])}: "
                               f"compensar à parte.")

        for doc, ps in bc.items():
            soma = round(sum(p["valor"] for p in ps), 2)
            deb = [p for p in ps if p["valor"] > 0]
            cre = [p for p in ps if p["valor"] < 0]
            mesma_data = len({p["data_doc"] for p in ps}) == 1
            outras = sorted(lojas_do_doc[doc] - {atrib})
            # contrapartida só vale dentro da mesma loja (atribuição)
            par_na_loja = len(ps) == 2 and len(deb) == 1 and len(cre) == 1 and soma == 0 and mesma_data
            ok = par_na_loja and not outras
            if not ok:
                if par_na_loja:
                    motivo = (f"par completo, mas o mesmo nº de documento tem lançamento na(s) loja(s) "
                              f"{', '.join(outras)}; a F.13 seleciona por número e incluiria esse lançamento. "
                              f"Compensar à mão")
                elif len(ps) == 2 and len(deb) == 1 and len(cre) == 1 and soma == 0:
                    motivo = "débito e crédito com datas DOC diferentes"
                elif cre and not deb:
                    motivo = f"só crédito de {brl(-cre[0]['valor'])}. Falta o débito desta loja"
                elif deb and not cre:
                    motivo = f"só débito de {brl(deb[0]['valor'])}. Falta o crédito desta loja"
                else:
                    motivo = f"{len(ps)} linhas, saldo {brl(soma)}"
                if outras and not par_na_loja:
                    motivo += (f" (o lançamento do mesmo documento na loja {', '.join(outras)} "
                               f"não é contrapartida)")
                erros.append(f"Doc. {doc} ({ps[0]['data_doc']:%d/%m}): {motivo}.")
            docs.append({
                "doc": doc,
                "data_doc": ps[0]["data_doc"].isoformat(),
                "data_lanc": max(p["data_lanc"] for p in ps).isoformat(),
                "valor": max(abs(p["valor"]) for p in ps),
                "soma": soma,
                "linhas": len(ps),
                "ok": ok,
            })
        docs.sort(key=lambda d: (d["data_doc"], d["doc"]))

        pares = [d for d in docs if d["ok"]]
        valores = sorted({d["valor"] for d in pares})
        if len(valores) > 1:
            revisar.append("Pares com valores diferentes: " + " e ".join(brl(v) for v in valores) + ".")
        if fundo is not None and valores and any(v != fundo for v in valores):
            revisar.append(f"Fecha com {' e '.join(brl(v) for v in valores)}, mas o fundo de referência "
                           f"é {brl(fundo)}.")
        if fundo is None and pares:
            avisos.append("Sem partida inicial (SE/AB) para conferir o fundo.")

        por_dia = defaultdict(list)
        for d in pares:
            por_dia[d["data_doc"]].append(d["doc"])
        for dia, ds in sorted(por_dia.items()):
            if len(ds) > 1:
                revisar.append(f"{len(ds)} fechamentos com data DOC {date.fromisoformat(dia):%d/%m}: "
                               f"{' e '.join(ds)}.")

        todos_dias = {d["data_doc"] for d in docs}
        if todos_dias:
            dias = sorted(date.fromisoformat(d) for d in todos_dias)
            atual, faltam = dias[0], []
            while atual < dias[-1]:
                atual += timedelta(days=1)
                if atual.isoformat() not in todos_dias:
                    faltam.append(f"{atual:%d/%m}")
            if faltam:
                avisos.append("Sem fechamento em aberto em " + ", ".join(faltam) +
                              ". Pode já ter sido compensado.")

        if erros:
            status = "erro"
        elif revisar:
            status = "revisar"
        elif pares:
            status = "ok"
        else:
            status = "sem_movimento"

        lojas.append({
            "atrib": atrib,
            "status": status,
            "fundo": fundo,
            "erros": erros,
            "revisar": revisar,
            "avisos": avisos,
            "docs": docs,
            "antigas": [{
                "doc": p["doc"], "tipo": p["tipo"], "data_doc": p["data_doc"].isoformat(),
                "valor": p["valor"], "texto": p["texto"],
            } for p in sorted(antigas, key=lambda p: p["data_doc"])],
        })
    return lojas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo")
    ap.add_argument("--mes", help="mês de referência AAAA-MM (padrão: mês atual)")
    ap.add_argument("--saida", default=".")
    ap.add_argument("--demo", action="store_true", help="marca a página como dados fictícios")
    a = ap.parse_args()

    hoje = date.today()
    inicio = (datetime.strptime(a.mes, "%Y-%m").date() if a.mes else hoje.replace(day=1))
    partidas = ler_exportacao(a.arquivo)
    lojas = analisar(partidas, inicio)

    dados = {
        "arquivo": Path(a.arquivo).name,
        "conta": "28200202",
        "mes_ref": inicio.isoformat(),
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "total_linhas": len(partidas),
        "lojas": lojas,
        "demo": a.demo,
    }
    out = Path(a.saida)
    (out / "analise.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    tpl = (Path(__file__).parent / "modelo_revisao.html").read_text(encoding="utf-8")
    html = tpl.replace("/*__DADOS__*/null", json.dumps(dados, ensure_ascii=False))
    (out / "revisao_compensacao.html").write_text(html, encoding="utf-8")

    cont = defaultdict(int)
    for l in lojas:
        cont[l["status"]] += 1
    print(f"{len(partidas)} partidas lidas, {len(lojas)} lojas | "
          f"ok {cont['ok']} | revisar {cont['revisar']} | erro {cont['erro']} | sem movimento {cont['sem_movimento']}")
    for l in lojas:
        for m in l["erros"] + l["revisar"]:
            print(f"  {l['atrib']} [{l['status']}] {m}")


if __name__ == "__main__":
    main()
