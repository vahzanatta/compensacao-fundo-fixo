# Gera uma exportação FBL3H fictícia (mesmo layout do SAP) com os cenários que a análise trata.
from datetime import date, timedelta

H = ["Empresa", "Código da moeda empresa", "Conta do Razão", "Data do documento", "Data de lançamento",
     "Nº documento", "Tipo de documento", "Valor em moeda da empresa", "Chave de lançamento", "Atribuição", "Texto"]
TD = "X8GLFCO-STOREX - FECHAMENTO DE CAIXA - FCAIXD"
TC = "X8GLFCO-STOREX - FECHAMENTO DE CAIXA - FCAIXC"
seq = [1399000100]
linhas = []


def fmt(v):
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if v < 0 else "") + s


def lin(dd, dl, doc, tp, v, atr, txt):
    linhas.append(["BR21", "BRL", "28200202", f"{dd:%d/%m/%Y}", f"{dl:%d/%m/%Y}", doc, tp, fmt(v),
                   "40" if v > 0 else "50", atr, txt])


def novo_doc():
    seq[0] += 1
    return str(seq[0])


def par(atr, dd, v, atraso=1):
    doc = novo_doc()
    dl = dd + timedelta(days=atraso)
    lin(dd, dl, doc, "BC", -v, atr, TC)
    lin(dd, dl, doc, "BC", v, atr, TD)


def abertura(atr, v, dd=date(2024, 3, 4), tp="SE"):
    lin(dd, dd, "80009" + atr[-4:], tp, v, atr, f"FUNDO FIXO ABERTURA LOJA {atr}")


out = date(2026, 10, 1)
dias = [out + timedelta(days=i) for i in range(7)]  # 01 a 07/10

# Lojas sem problema
for atr, v in [("09101", 15000), ("09102", 15000), ("09103", 12000), ("09104", 10000), ("09105", 15000), ("09106", 18000)]:
    abertura(atr, v)
    for d in dias:
        par(atr, d, v, atraso=1 if d.weekday() < 5 else 2)

# 09107: um dia só com o crédito (importou metade)
abertura("09107", 15000)
for d in dias:
    if d == date(2026, 10, 5):
        lin(d, d + timedelta(days=1), novo_doc(), "BC", -15000, "09107", TC)
    else:
        par("09107", d, 15000)

# 09108: dois fechamentos com a mesma data DOC
abertura("09108", 15000)
for d in dias:
    par("09108", d, 15000)
par("09108", date(2026, 10, 4), 15000, atraso=3)

# 09109: redução de fundo (15 -> 10 mil) com lançamento de acerto no mês
abertura("09109", 15000)
lin(date(2026, 10, 3), date(2026, 10, 3), "80010" + "9109", "SA", -5000, "09109", "AJUSTE FUNDO FIXO LOJA 9109")
for d in dias:
    par("09109", d, 15000 if d < date(2026, 10, 3) else 10000)

# 09110: dias sem fechamento em aberto
abertura("09110", 15000)
for d in dias:
    if d not in (date(2026, 10, 3), date(2026, 10, 4)):
        par("09110", d, 15000)

# 09111: nada em aberto no mês
abertura("09111", 15000)

# 09112: abertura tipo AB e um débito antigo sem par (fora do escopo)
abertura("09112", 12000, date(2024, 8, 12), "AB")
lin(date(2024, 9, 2), date(2024, 9, 3), "1300489999", "BC", 12000, "09112", TD)
for d in dias:
    par("09112", d, 12000)

# 09113: fechamento retroativo (data DOC 30/09, lançado 02/10) fica antes do mês
abertura("09113", 15000)
par("09113", date(2026, 9, 30), 15000, atraso=2)
for d in dias:
    par("09113", d, 15000)

linhas.sort(key=lambda l: (l[3][6:] + l[3][3:5] + l[3][:2], l[5]))
with open("fbl3h_ficticio.txt", "w", encoding="utf-8") as f:
    f.write("\t".join(H) + "\n" + "\n".join("\t".join(l) for l in linhas) + "\n")
print(len(linhas), "linhas")
