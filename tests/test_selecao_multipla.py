"""
Testes da digitação e da releitura da seleção múltipla da F.13, com uma tabela falsa
que imita a do SAP GUI. Não precisam de SAP.

A tabela falsa reproduz o que foi visto no SAP real: com 8 linhas visíveis e 8 documentos
digitados, pedir a posição 8 da barra de rolagem para na 7. O código antigo escrevia o 9º
documento por cima do 8º e a conferência acusava "esperados 10, lidos 9".
"""
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fundo_fixo  # noqa: E402


class TabelaFalsa:
    def __init__(self, visiveis=8, maximo_fixo=None):
        self.visiveis = visiveis
        self.linhas = {}            # posição absoluta -> texto
        self.pos = 0
        self.maximo_fixo = maximo_fixo  # simula um SAP que nunca deixa rolar além disso
        self.enters = 0

    def maximo(self):
        if self.maximo_fixo is not None:
            return self.maximo_fixo
        preenchidas = max(self.linhas, default=-1) + 1
        return max(0, preenchidas - 1)


class _Barra:
    def __init__(self, tab):
        self._tab = tab

    @property
    def Maximum(self):
        return self._tab.maximo()

    @property
    def position(self):
        return self._tab.pos

    @position.setter
    def position(self, valor):
        self._tab.pos = min(max(0, valor), self._tab.maximo())


class _Celula:
    def __init__(self, tab, linha):
        self._tab, self._linha = tab, linha

    @property
    def text(self):
        return self._tab.linhas.get(self._tab.pos + self._linha, "")

    @text.setter
    def text(self, valor):
        self._tab.linhas[self._tab.pos + self._linha] = valor


class SessaoFalsa:
    def __init__(self, tab):
        self.tab = tab

    def findById(self, id_):
        if id_ == fundo_fixo.TABELA_SELECAO:
            return type("Tabela", (), {"VisibleRowCount": self.tab.visiveis,
                                       "verticalScrollbar": _Barra(self.tab)})()
        m = re.search(r"txtRSCSEL_255-SLOW_I\[1,(\d+)\]$", id_)
        if m:
            linha = int(m.group(1))
            if linha >= self.tab.visiveis:
                raise Exception("linha fora da tela")
            return _Celula(self.tab, linha)
        if id_ == "wnd[1]":
            tab = self.tab
            return type("Janela", (), {"sendVKey": lambda _self, k: setattr(tab, "enters", tab.enters + 1)})()
        raise Exception(f"id desconhecido: {id_}")


def documentos(n):
    return [str(1399000100 + i) for i in range(1, n + 1)]


@mock.patch("fundo_fixo.time.sleep", lambda *_: None)
class SelecaoMultipla(unittest.TestCase):
    def test_digita_e_rele_qualquer_quantidade(self):
        for n in (1, 7, 8, 9, 10, 20, 35):
            with self.subTest(documentos=n):
                s = SessaoFalsa(TabelaFalsa())
                docs = documentos(n)
                fundo_fixo.digitar_documentos(s, docs)
                self.assertEqual([s.tab.linhas[i] for i in range(n)], docs, "a tabela não ficou na ordem")
                self.assertEqual(fundo_fixo.ler_selecao(s), docs)
                fundo_fixo.conferir_selecao(s, docs)  # não pode levantar erro

    def test_dez_documentos_nao_apaga_o_oitavo(self):  # o caso visto no SAP real
        s = SessaoFalsa(TabelaFalsa())
        docs = documentos(10)
        fundo_fixo.digitar_documentos(s, docs)
        self.assertIn(docs[7], s.tab.linhas.values())

    def test_selecao_vazia(self):
        self.assertEqual(fundo_fixo.ler_selecao(SessaoFalsa(TabelaFalsa())), [])

    def test_para_com_erro_se_a_tabela_nao_rolar(self):
        s = SessaoFalsa(TabelaFalsa(maximo_fixo=0))
        with self.assertRaises(RuntimeError):
            fundo_fixo.digitar_documentos(s, documentos(10))

    def test_conferencia_acusa_documento_apagado(self):
        s = SessaoFalsa(TabelaFalsa())
        docs = documentos(10)
        fundo_fixo.digitar_documentos(s, docs)
        s.tab.linhas[7] = docs[8]  # simula a sobrescrita antiga
        with self.assertRaises(RuntimeError):
            fundo_fixo.conferir_selecao(s, docs)


if __name__ == "__main__":
    unittest.main()
