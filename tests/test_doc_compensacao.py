"""
Conferência da quantidade de docs de compensação por loja. Não precisa de SAP.

No SAP real (15/10/2026), a F.13 gerou um doc. de compensação por data de lançamento dentro
da loja: 10 documentos com 8 datas de lançamento geraram 8 docs, e o app só achou 6 na saída.
Agora o app compara com o esperado e grava um aviso no histórico quando não bate.
"""
import csv
import sys
import tempfile
import types
import unittest
from collections import OrderedDict
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fundo_fixo  # noqa: E402
from test_regras import com_fundos, escrever_fbl3h, partida  # noqa: E402


def par_lancado(atrib, doc, dia_doc, dia_lanc, valor=15000.0):
    return [dict(partida(atrib, doc, -valor, dia_doc), data_lanc=dia_lanc),
            dict(partida(atrib, doc, valor, dia_doc), data_lanc=dia_lanc)]


def caso_do_sap():
    """10 documentos da loja 09001 com 8 datas de lançamento (dois pares de dias repetidos)."""
    lanc = [date(2026, 10, d) for d in (2, 3, 3, 5, 6, 7, 7, 8, 9, 10)]
    docs = [str(1399000101 + i) for i in range(10)]
    partidas = []
    for i, (doc, dl) in enumerate(zip(docs, lanc)):
        partidas += par_lancado("09001", doc, date(2026, 10, 1) + timedelta(days=i), dl)
    return docs, com_fundos(partidas)


class Esperado(unittest.TestCase):
    def test_um_por_data_de_lancamento(self):
        docs, partidas = caso_do_sap()
        abertas = {}
        for p in partidas:
            abertas.setdefault((p["atrib"], p["doc"]), []).append(p)
        self.assertEqual(fundo_fixo.docs_comp_esperados(abertas, "09001", docs), 8)
        self.assertEqual(fundo_fixo.docs_comp_esperados(abertas, "09001", docs[:1]), 1)

    def test_aviso(self):
        self.assertEqual(fundo_fixo.aviso_doc_comp(["1", "2"], 2), "")
        self.assertIn("6 de 8", fundo_fixo.aviso_doc_comp([str(i) for i in range(6)], 8))
        self.assertIn("3 de 2", fundo_fixo.aviso_doc_comp(["1", "2", "3"], 2))


class _ListaFalsa:
    """Lista de saída da F.13 (SAPF124) com rolagem: só `por_pagina` linhas visíveis por vez."""

    def __init__(self, linhas, por_pagina, com_barra=True):
        self.linhas, self.por_pagina, self.pos, self.com_barra = linhas, por_pagina, 0, com_barra

    @property
    def maximo(self):
        return max(0, len(self.linhas) - self.por_pagina)


class _Barra:
    def __init__(self, lista):
        self._l = lista

    maximum = property(lambda self: self._l.maximo)
    pageSize = property(lambda self: self._l.por_pagina)

    @property
    def position(self):
        return self._l.pos

    @position.setter
    def position(self, v):
        self._l.pos = min(max(0, v), self._l.maximo)


class _Usr:
    def __init__(self, lista):
        self._l = lista
        visiveis = lista.linhas[lista.pos:lista.pos + lista.por_pagina]
        self.Children = types.SimpleNamespace(Count=len(visiveis),
                                              ElementAt=lambda i: types.SimpleNamespace(Text=visiveis[i]))

    @property
    def verticalScrollbar(self):
        if not self._l.com_barra:
            raise Exception("sem barra de rolagem")
        return _Barra(self._l)


def saida_f13(n_grupos):
    """Imita a lista do SAP: cabeçalho e, por grupo, 2 linhas de documento e 1 de total (números fictícios)."""
    linhas = ["Compensação automática", "Exec.efet.  Lista detalhada de itens em aberto e compensados",
              "Empresa", "BR21", "Nº conta", "28200202", "Nº doc.", "DocCompens"]
    for g in range(n_grupos):
        doc, comp = str(1399000101 + g), str(900000001 + g)
        linhas += [doc, "001", "15.10.2026", comp, "BRL", "15.000,00-", "09001", f"202610{g + 1:02d}",
                   doc, "002", "15.10.2026", comp, "BRL", "15.000,00", "09001", f"202610{g + 1:02d}",
                   "*", "15.10.2026", comp, "BRL", "0,00"]
    return linhas, [str(1399000101 + g) for g in range(n_grupos)], [str(900000001 + g) for g in range(n_grupos)]


@mock.patch("fundo_fixo.time.sleep", lambda *_: None)
class ListaDeSaida(unittest.TestCase):
    """Caso visto no SAP em 15/10/2026: 8 docs de compensação, a primeira página mostrava só 5."""

    def sessao(self, lista):
        return types.SimpleNamespace(findById=lambda id_: _Usr(lista))

    def test_le_todas_as_paginas(self):
        linhas, docs, comps = saida_f13(8)
        lista = _ListaFalsa(linhas, por_pagina=8 + 5 * 21)  # cabeçalho + 5 grupos, como no SAP
        texto = fundo_fixo.textos_da_lista(self.sessao(lista))
        self.assertEqual(fundo_fixo.docs_compensacao(texto, docs), comps)

    def test_paginas_pequenas(self):
        linhas, docs, comps = saida_f13(20)
        texto = fundo_fixo.textos_da_lista(self.sessao(_ListaFalsa(linhas, por_pagina=7)))
        self.assertEqual(fundo_fixo.docs_compensacao(texto, docs), comps)

    def test_sem_barra_le_a_tela_que_houver(self):
        linhas, docs, comps = saida_f13(8)
        texto = fundo_fixo.textos_da_lista(self.sessao(_ListaFalsa(linhas, 8 + 5 * 21, com_barra=False)))
        self.assertEqual(fundo_fixo.docs_compensacao(texto, docs), comps[:5])


@mock.patch("fundo_fixo.time.sleep", lambda *_: None)
class CompensacaoEfetivaFalsa(unittest.TestCase):
    """Roda executar_compensacao com SAP falso e confere o que vai para o histórico."""

    def rodar(self, achados):
        docs, partidas = caso_do_sap()
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        p = Path(pasta.name)
        txt = escrever_fbl3h(partidas, p)
        sessao = types.SimpleNamespace(findById=lambda _id: types.SimpleNamespace(text="", sendVKey=lambda k: None))
        with mock.patch.dict(sys.modules, {"pythoncom": types.SimpleNamespace(CoInitialize=lambda: None,
                                                                             CoUninitialize=lambda: None)}), \
             mock.patch.multiple(fundo_fixo, PASTA_LOG=p / "logs", ARQ_HISTORICO=p / "historico.csv",
                                 ler_lista=lambda: OrderedDict([("09001", docs)]),
                                 rodar_relatorio=lambda: txt, sessao_sap=lambda: sessao,
                                 f13_loja=lambda s, d, teste: ("ok", "saída da F.13", achados),
                                 gerar_pagina=lambda t: None):
            resultados, conclusao = fundo_fixo.executar_compensacao(efetivo=True)
        with open(p / "historico.csv", encoding="utf-8-sig", newline="") as f:
            hist = list(csv.DictReader(f, delimiter=";"))
        return resultados, conclusao, hist

    def test_incompleto_vira_aviso_no_historico(self):
        resultados, conclusao, hist = self.rodar([str(1500000231 + i) for i in range(6)])
        self.assertEqual(hist[0]["status"], "ok")  # o SAP compensou: não é erro
        self.assertTrue(hist[0]["mensagem_sap"].startswith("Conferir doc. de compensação"))
        self.assertIn("6 de 8", hist[0]["mensagem_sap"])
        self.assertIn("6 de 8", resultados[0]["aviso"])
        self.assertIn("conferir", conclusao.lower())

    def test_completo_sem_aviso(self):
        resultados, _, hist = self.rodar([str(1500000231 + i) for i in range(8)])
        self.assertFalse(hist[0]["mensagem_sap"].startswith("Conferir"))
        self.assertEqual(resultados[0]["aviso"], "")


if __name__ == "__main__":
    unittest.main()
