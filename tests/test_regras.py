"""
Testes das regras de negócio (CLAUDE.md, "Regras de negócio"). Não precisam de SAP.

Rodar na pasta do projeto:
    py -m unittest discover -s tests -v
"""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import analisar  # noqa: E402
import fundo_fixo  # noqa: E402

FICTICIO = RAIZ / "exemplos" / "fbl3h_ficticio.txt"
OUTUBRO = date(2026, 10, 1)


def partida(atrib, doc, valor, dia=date(2026, 10, 2), tipo="BC"):
    return {"data_doc": dia, "data_lanc": dia, "doc": doc, "tipo": tipo, "valor": valor,
            "chave": "40" if valor > 0 else "50", "atrib": atrib, "texto": ""}


def par(atrib, doc, valor=15000.0, dia=date(2026, 10, 2)):
    return [partida(atrib, doc, -valor, dia), partida(atrib, doc, valor, dia)]


def abertura(atrib, valor=15000.0, tipo="SE", dia=date(2024, 3, 4)):
    """Fundo de referência: o lançamento mais antigo da loja."""
    return partida(atrib, "8000" + atrib, valor, dia, tipo)


def com_fundos(partidas):
    """Acrescenta a abertura de cada loja que aparece nas partidas (toda loja precisa ter fundo)."""
    lojas = sorted({p["atrib"] for p in partidas})
    return [abertura(a) for a in lojas] + partidas


def por_loja(lojas):
    return {l["atrib"]: l for l in lojas}


def escrever_fbl3h(partidas, pasta):
    """Grava uma FBL3H falsa (mesmo layout da exportação) e devolve o caminho."""
    cab = ["Empresa", "Data do documento", "Data de lançamento", "Nº documento", "Tipo de documento",
           "Valor em moeda da empresa", "Chave de lançamento", "Atribuição", "Texto"]
    linhas = ["\t".join(cab)]
    for p in partidas:
        linhas.append("\t".join(["BR21", f"{p['data_doc']:%d.%m.%Y}", f"{p['data_lanc']:%d.%m.%Y}",
                                 p["doc"], p["tipo"], analisar.brl(p["valor"]), p["chave"],
                                 p["atrib"], ""]))
    caminho = pasta / "fbl3h.txt"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


class ExemploFicticio(unittest.TestCase):
    """Cada loja fictícia (09101 a 09113) representa uma situação; o status não pode mudar sem querer."""

    @classmethod
    def setUpClass(cls):
        cls.lojas = por_loja(analisar.analisar(analisar.ler_exportacao(FICTICIO), OUTUBRO))

    def test_status_de_cada_loja(self):
        esperado = {
            "09101": "ok", "09102": "ok", "09103": "ok", "09104": "ok", "09105": "ok", "09106": "ok",
            "09107": "erro", "09108": "revisar", "09109": "revisar", "09110": "ok",
            "09111": "sem_movimento", "09112": "ok", "09113": "ok",
        }
        self.assertEqual({a: l["status"] for a, l in self.lojas.items()}, esperado)

    def test_partida_inicial_nunca_entra(self):
        for l in self.lojas.values():
            self.assertFalse([d for d in l["docs"] if d["doc"].startswith("80009")], l["atrib"])

    def test_retroativo_do_mes_anterior_fica_fora(self):
        docs = self.lojas["09113"]["docs"]
        self.assertTrue(all(d["data_doc"] >= "2026-10-01" for d in docs))
        self.assertTrue(any(p["data_doc"] == "2026-09-30" for p in self.lojas["09113"]["antigas"]))

    def test_documento_sem_par_fica_bloqueado(self):
        bloqueados = [d for d in self.lojas["09107"]["docs"] if not d["ok"]]
        self.assertEqual(len(bloqueados), 1)

    def test_lancamento_nao_bc_manda_revisar(self):
        self.assertTrue(any("SA" in m for m in self.lojas["09109"]["revisar"]))


class RegrasDoPar(unittest.TestCase):
    def analisa(self, partidas):
        return por_loja(analisar.analisar(com_fundos(partidas), OUTUBRO))

    def test_par_correto(self):
        l = self.analisa(par("09001", "100"))["09001"]
        self.assertEqual(l["status"], "ok")
        self.assertTrue(l["docs"][0]["ok"])

    def test_numero_em_outra_loja_bloqueia_o_par(self):  # regra 7
        lojas = self.analisa(par("09001", "100") + [partida("09002", "100", 50.0)])
        self.assertEqual(lojas["09001"]["status"], "erro")
        self.assertFalse(lojas["09001"]["docs"][0]["ok"])

    def test_outra_loja_nunca_e_contrapartida(self):  # regra 6
        lojas = self.analisa([partida("09001", "100", -15000.0), partida("09002", "100", 15000.0)])
        self.assertEqual(lojas["09001"]["status"], "erro")
        self.assertEqual(lojas["09002"]["status"], "erro")

    def test_datas_diferentes_bloqueiam(self):  # regra 8
        ps = [partida("09001", "100", -15000.0, date(2026, 10, 2)),
              partida("09001", "100", 15000.0, date(2026, 10, 3))]
        self.assertEqual(self.analisa(ps)["09001"]["status"], "erro")

    def test_mais_de_duas_linhas_bloqueia(self):
        ps = par("09001", "100") + [partida("09001", "100", 10.0), partida("09001", "100", -10.0)]
        self.assertEqual(self.analisa(ps)["09001"]["status"], "erro")

    def test_valor_diferente_do_fundo_manda_revisar(self):
        ps = par("09001", "100", 12000.0)  # o fundo de com_fundos é 15.000,00
        self.assertEqual(self.analisa(ps)["09001"]["status"], "revisar")

    def test_dois_fechamentos_na_mesma_data_manda_revisar(self):
        ps = par("09001", "100") + par("09001", "101")
        self.assertEqual(self.analisa(ps)["09001"]["status"], "revisar")


class FundoDeReferencia(unittest.TestCase):
    """Regra 1: o fundo é o documento mais antigo da loja (data DOC), de qualquer tipo, com saldo a débito.
    Nunca é compensado. Loja sem fundo é erro e fica inteira fora do lote."""

    def analisa(self, partidas):
        return por_loja(analisar.analisar(partidas, OUTUBRO))["09001"]

    def test_fundo_de_qualquer_tipo(self):
        for tipo in ("SE", "AB", "SA", "BC", "ZZ"):
            with self.subTest(tipo=tipo):
                l = self.analisa([abertura("09001", 15000.0, tipo)] + par("09001", "100"))
                self.assertEqual(l["fundo"], 15000.0)
                self.assertEqual(l["status"], "ok")
                self.assertEqual([d["doc"] for d in l["docs"]], ["100"])

    def test_fundo_lancado_no_mes_nao_entra_no_lote(self):
        ps = [abertura("09001", 15000.0, "BC", date(2026, 10, 1))] + par("09001", "100")
        l = self.analisa(ps)
        self.assertEqual(l["status"], "ok")
        self.assertNotIn("800009001", [d["doc"] for d in l["docs"]])

    def test_se_que_nao_e_o_mais_antigo_vai_para_revisar(self):
        ps = [abertura("09001"), partida("09001", "500", -15000.0, date(2026, 10, 3), "SE")] + par("09001", "100")
        l = self.analisa(ps)
        self.assertEqual(l["fundo"], 15000.0)
        self.assertEqual(l["status"], "revisar")

    def test_loja_sem_fundo_e_erro_e_fica_toda_fora(self):
        l = self.analisa(par("09001", "100", dia=date(2026, 10, 1)) + par("09001", "101", dia=date(2026, 10, 2)))
        self.assertEqual(l["status"], "erro")
        self.assertTrue(any("fundo" in m for m in l["erros"]))
        self.assertFalse([d for d in l["docs"] if d["ok"]])

    def test_mais_antigo_a_credito_nao_e_fundo(self):
        ps = [abertura("09001", -500.0)] + par("09001", "100")
        l = self.analisa(ps)
        self.assertEqual(l["status"], "erro")
        self.assertFalse([d for d in l["docs"] if d["ok"]])

    def test_desempate_pela_data_de_lancamento_e_pelo_numero(self):
        a = dict(abertura("09001", 15000.0), doc="900", data_lanc=date(2024, 3, 6))
        b = dict(abertura("09001", 12000.0), doc="901", data_lanc=date(2024, 3, 5))
        self.assertEqual(self.analisa([a, b] + par("09001", "100", 12000.0))["fundo"], 12000.0)
        c = dict(abertura("09001", 12000.0), doc="899", data_lanc=date(2024, 3, 6))
        self.assertEqual(self.analisa([a, c] + par("09001", "100", 12000.0))["fundo"], 12000.0)


class ParValidoDaCompensacao(unittest.TestCase):
    """par_valido (fundo_fixo.py) repete a regra do par de analisar.py; os dois têm que concordar."""

    def test_par_correto(self):
        self.assertIsNone(fundo_fixo.par_valido(par("09001", "100")))

    def test_recusa(self):
        casos = {
            "uma linha": [partida("09001", "100", 15000.0)],
            "dois débitos": [partida("09001", "100", 15000.0), partida("09001", "100", 15000.0)],
            "valores diferentes": [partida("09001", "100", 15000.0), partida("09001", "100", -14000.0)],
            "datas diferentes": [partida("09001", "100", 15000.0, date(2026, 10, 2)),
                                 partida("09001", "100", -15000.0, date(2026, 10, 3))],
            "tipo não BC": [partida("09001", "100", 15000.0, tipo="SA"),
                            partida("09001", "100", -15000.0, tipo="SA")],
        }
        for nome, linhas in casos.items():
            with self.subTest(nome):
                self.assertIsNotNone(fundo_fixo.par_valido(linhas))


class RevalidacaoAntesDaF13(unittest.TestCase):
    """Regra 11: o lote é conferido com a FBL3H extraída de novo antes de executar."""

    def relatorio(self, partidas, fundos=True):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        return escrever_fbl3h(com_fundos(partidas) if fundos else partidas, Path(pasta.name))

    def test_lote_valido_passa(self):
        txt = self.relatorio(par("09001", "100") + par("09002", "200"))
        self.assertEqual(fundo_fixo.validar_com_relatorio({"09001": ["100"], "09002": ["200"]}, txt), [])

    def test_documento_que_saiu_do_aberto_falha(self):
        txt = self.relatorio(par("09001", "100"))
        self.assertTrue(fundo_fixo.validar_com_relatorio({"09001": ["100", "101"]}, txt))

    def test_numero_em_outra_loja_falha(self):
        txt = self.relatorio(par("09001", "100") + [partida("09002", "100", 50.0)])
        self.assertTrue(fundo_fixo.validar_com_relatorio({"09001": ["100"]}, txt))

    def test_fundo_de_referencia_no_lote_falha(self):  # regra 1, mesmo se o fundo for um "par" BC
        fundo = par("09001", "90", dia=date(2024, 3, 4))
        fundo[1]["valor"] = 30000.0  # débito maior: saldo a débito, vale como fundo
        txt = self.relatorio(fundo + par("09001", "100"), fundos=False)
        self.assertTrue(fundo_fixo.validar_com_relatorio({"09001": ["90", "100"]}, txt))

    def test_loja_sem_fundo_falha(self):
        txt = self.relatorio(par("09001", "100", dia=date(2026, 10, 1)) + par("09001", "101"), fundos=False)
        problemas = fundo_fixo.validar_com_relatorio({"09001": ["101"]}, txt)
        self.assertTrue(any("fundo" in p for p in problemas))


class LoteVindoDaTela(unittest.TestCase):
    def test_recusa_lote_invalido(self):
        casos = {
            "cabeçalho errado": "loja;doc\n09001;100\n",
            "vazio": "atribuicao;documento;data_doc;valor\n",
            "linha com letras": "atribuicao;documento;data_doc;valor\n09001;ABC;02/10/2026;15000\n",
        }
        for nome, texto in casos.items():
            with self.subTest(nome), self.assertRaises(fundo_fixo.Falha):
                fundo_fixo.salvar_lista(texto)


class DocDeCompensacao(unittest.TestCase):
    def test_ignora_documentos_do_lote_e_a_conta(self):
        texto = "Doc 1399000101 e 1399000102 compensados com 0100012345; conta 0028200202"
        self.assertEqual(fundo_fixo.docs_compensacao(texto, ["1399000101", "1399000102"]), ["100012345"])


if __name__ == "__main__":
    unittest.main()
