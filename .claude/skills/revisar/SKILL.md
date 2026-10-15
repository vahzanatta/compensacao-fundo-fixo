---
name: revisar
description: Checklist de revisão do projeto de compensação do fundo fixo. Use antes de todo commit ou PR neste repositório, e sempre que a Vah pedir para revisar uma mudança. Confere regras de negócio, travas de segurança da F.13, codificação, documentação e testes.
---

# Revisão de mudança: compensação do fundo fixo

Revise o que mudou (`git diff` e `git diff --staged`, mais arquivos novos em `git status`). Responda em português, direto, para a Vah, que não é programadora: diga o que achou, o risco em termos de SAP e o que fazer.

## 1. Rodar o que dá para rodar
- `py -m unittest discover -s tests -v`: todos precisam passar.
- Se mexeu em `analisar.py` ou `modelo_revisao.html`: `py analisar.py exemplos/fbl3h_ficticio.txt --mes 2026-10 --saida <pasta temporária>`. O resumo esperado é "ok 9 | revisar 2 | erro 1 | sem movimento 1".
- Mostre a saída. Se algo não pôde ser rodado, diga.

## 2. Travas de segurança (bloqueia o commit se alguma cair)
Confira no diff que nenhuma destas foi removida ou enfraquecida sem confirmação explícita da Vah na conversa:
- partida SE/AB nunca entra no lote;
- corte pela data DOC a partir do dia 1º do mês;
- par = mesmo documento, mesma loja, 1 débito + 1 crédito, tipo BC, soma zero, mesma data DOC;
- documento com o número em outra loja fica bloqueado;
- lote só com saldo 0,00;
- FBL3H extraída de novo e `validar_com_relatorio` antes de testar ou compensar; qualquer falha para tudo;
- seleção múltipla conferida (`conferir_selecao`) e vazia antes de digitar;
- compensação efetiva exige confirmação na tela; padrão é teste (`X_TESTL`).

## 3. Regras de negócio
- Se a regra do par mudou em `analisar.py`, mudou igual em `fundo_fixo.par_valido`/`validar_com_relatorio` (e vice-versa)?
- A mudança tem teste em `tests/test_regras.py`?
- CLAUDE.md, README.md e `docs/fluxo.html` foram atualizados?

## 3b. Intent Layer
- Mexeu numa subpasta com `CLAUDE.md` (`docs/`, `exemplos/`)? O que ele diz continua verdade? Se a mudança criou um contrato novo ou uma armadilha, ela foi anotada lá.
- Mudou o papel de um arquivo da raiz? A tabela "Dono de / Não faz" e os invariantes globais do CLAUDE.md da raiz continuam certos.
- Mudou `modelo_revisao.html`, `analisar.py` ou os exemplos? A `docs/demonstracao.html` foi gerada de novo (como manda `docs/CLAUDE.md`).
- Continua existindo um só arquivo de contexto na raiz (sem `AGENTS.md`), e cada nó tem menos de ~4 mil tokens.

## 4. Padrões (seção "Padrões de código" do CLAUDE.md)
- Nenhuma dependência nova fora da biblioteca padrão, `pywin32` e `pywebview`.
- Erros para a analista com `Falha`, mensagem clara; nenhuma exceção engolida em código que decide compensação.
- Caminhos só por constantes/`config.ini`.
- `.vbs` sem acentos fora de comentários antigos (use `ChrW`); CSV em `utf-8-sig` com `;`.
- IDs do SAP GUI só de gravações reais; nada inventado.
- Mudança focada, sem reformatação ou refatoração não pedida.

## 5. Dados e segredos
- Nenhum `.txt`/`.csv` real do SAP, `config.ini`, `logs/` ou dado de loja real no commit (`git status` e `git diff --staged --stat`).
- Nenhuma senha, usuário ou caminho pessoal novo no código.

## Resultado
Termine com uma lista curta:
- **Bloqueia**: o que precisa ser corrigido antes do commit.
- **Atenção**: riscos ou dúvidas para a Vah decidir.
- **Validar no SAP**: o que só o SAP real confirma (ex.: caminho de rede, telas novas).
Se estiver tudo certo, diga isso em uma linha. Não corrija nada sem a Vah pedir.
