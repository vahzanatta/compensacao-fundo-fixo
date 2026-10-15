# Contexto do projeto: compensação do fundo fixo SAMS

Você está assumindo um projeto em andamento. Leia este arquivo inteiro antes de mudar qualquer coisa.

## Quem sou e como prefiro trabalhar
- Sou a Vah, analista de contas. Conheço bem o SAP, mas não sou programadora e não trabalho com UI/UX.
- Responda em português, de forma conversacional e direta. Prefiro precisão a respostas tranquilizadoras: se algo não foi testado, diga.
- Há dois computadores Windows. O Python é chamado com `py`, não `python`, nos dois:
  - **este (pessoal)**, onde o código é desenvolvido: não tem SAP nem acesso à rede da empresa, então a pasta `\\brsvp0000009\...` não existe aqui. Teste só com o exemplo fictício e os testes.
  - **o da empresa**, onde o app roda de verdade: tem SAP, a pasta de rede, `pywin32` e `pywebview`. Tudo que depende de SAP ou da rede só é validado lá, pela Vah.
- Antes de mexer em algo que lança no SAP, me explique o que vai mudar. Teste primeiro com o exemplo fictício e o modo de teste da F.13.

## Intent Layer

**Antes de mexer em arquivos de uma subpasta, leia o `CLAUDE.md` dela**, com o propósito, os contratos e as armadilhas locais. Este é o único arquivo de contexto na raiz (não criar `AGENTS.md` aqui). Os nós filhos usam o nome `CLAUDE.md` para o Claude Code carregá-los sozinho.

- **Exemplos fictícios**: `exemplos/CLAUDE.md`. Dados falsos que alimentam os testes e a demonstração.
- **Documentação para pessoas**: `docs/CLAUDE.md`. Fluxo ilustrado e página de demonstração gerada.
- `tests/` e `.claude/skills/` não têm nó próprio: são simples, e o que importa está aqui e na skill `/revisar`.

O código fica todo na raiz, então o mapa por arquivo é este:

| Arquivo | Dono de | Não faz |
|---|---|---|
| `analisar.py` | ler a FBL3H, formar pares, classificar lojas | nada no SAP; não grava fora de `--saida` |
| `fundo_fixo.py` | app (servidor, janela), FBL3H e F.13 via SAP GUI, revalidação, histórico | não decide a classificação da loja (vem de `analisar.py`) |
| `modelo_revisao.html` | tela; recebe os dados em `/*__DADOS__*/null` | não valida o lote: o Python revalida tudo antes da F.13 |
| `relatorio_fbl3h.vbs` | exportar a FBL3H com o layout /AGING | não analisa; recebe pasta, empresa, conta e arquivo do Python |
| `Fundo Fixo.vbs`, `*.bat` | atalhos de abrir, instalar e diagnosticar | sem regra de negócio |

### Invariantes globais
- Nada é compensado sem passar por: lote com saldo 0,00, FBL3H extraída de novo, `validar_com_relatorio` sem nenhum problema, seleção múltipla relida, e confirmação na tela para a execução efetiva.
- A regra do par vive em `analisar.analisar` e em `fundo_fixo.par_valido`/`validar_com_relatorio`; as duas mudam juntas, com teste.
- Dados reais do SAP (`.txt`, `.csv`, logs) nunca entram no git.
- Tudo o que é gravado vai para `PASTA_RELATORIO` (rede) ou `PASTA_LOG` (app); nada em caminho fixo.

## O problema
- A conta 28200202 (empresa BR21) é compensável. As 58 lojas SAMS lançam todo dia um débito e um crédito do fundo fixo (tipo BC), importados do Storex quando o caixa fecha.
- Toda sexta eu compensava manualmente pela FBL3H e F-03, loja por loja: cerca de 600 a 700 partidas por semana.
- Uma macro anterior errava porque casava só pelo valor (pegava troco, vendas e depósitos que zeravam por coincidência).

## Regras de negócio (validadas comigo, não mudar sem confirmar)
1. A partida inicial (tipo SE ou AB) é o fundo de referência da loja e nunca é compensada.
2. Só entram partidas com data DOC a partir do dia 1º do mês corrente.
3. Atribuição = código da loja. As partidas são agrupadas por loja.
4. Um par é o mesmo nº de documento, na mesma loja: exatamente 1 débito e 1 crédito, tipo BC, que somam zero e têm a mesma data DOC.
5. Crédito = valor negativo (chave 50); débito = valor positivo (chave 40).
6. Lançamento de outra loja nunca é contrapartida, mesmo com o mesmo nº de documento.
7. Se o nº de um documento aparece também em outra loja, o par fica bloqueado, porque a F.13 seleciona por número e pegaria o outro lançamento.
8. Nunca compensar um crédito de um documento com um débito de outro, nem de datas diferentes.
9. Classificação das lojas:
   - **erro**: documento sem par, com mais de 2 linhas, datas diferentes ou número em outra loja. O documento fica bloqueado.
   - **revisar**: lançamento não BC, pares com valores diferentes, valor diferente do fundo, dois fechamentos na mesma data DOC.
   - **pronta**: tudo certo; já vem marcada.
   - **sem movimento**: nada em aberto no mês.
10. O lote só é montado com saldo da seleção igual a 0,00.
11. Antes de testar ou compensar, a FBL3H é extraída de novo e cada documento é revalidado. Se qualquer um falhar, nada é executado.
12. A compensação efetiva exige confirmação na tela.

## Como funciona hoje (versão 1)
- `Fundo Fixo.vbs` abre `fundo_fixo.py app` via `pyw`, sem terminal. Ele sobe um servidor local (`http.server`, porta 8765) e abre a tela numa janela pywebview (sem pywebview, abre no navegador padrão). Fechar a janela encerra tudo.
- `relatorio_fbl3h.vbs` exporta a FBL3H (layout /AGING) para `fundo_fixo.txt`. Recebe pasta, empresa, conta e nome do arquivo como argumentos.
- `analisar.py` concentra as regras de negócio: lê o TXT (aceita cabeçalho com nome técnico, como `Data doc. (BLDAT)`, e datas com ponto ou barra), forma os pares e classifica as lojas.
- `modelo_revisao.html` é a tela. Os dados entram no lugar de `/*__DADOS__*/null`. Tem busca, filtros, tema claro e escuro, botões Montar lote, Testar lote e Compensar lote, progresso por loja e Histórico.
- O nome que usamos é **lote de compensação**. O arquivo continua se chamando `a_compensar.csv`.
- F.13: uma execução por loja, porque a OB74 não tem critérios para a conta e, sem eles, a F.13 junta tudo num grupo só.
- IDs do SAP GUI vindos das minhas gravações:
  - campos da F.13: `chkX_SAKNR`, `ctxtBUKRX-LOW`, `txtGJAHX-LOW`, `ctxtKONTS-LOW`, `chkX_TESTL`;
  - botão da seleção múltipla: `btn%_DOCNR_%_APP_%-VALU_PUSH`;
  - tabela da seleção: `wnd[1]/usr/tabsTAB_STRIP/tabpSIVA/ssubSCREEN_HEADER:SAPLALDB:3010/tblSAPLALDBSINGLE/txtRSCSEL_255-SLOW_I[1,n]`;
  - confirmar: `wnd[1]/tbar[0]/btn[8]`.
- Os documentos são digitados linha a linha na seleção múltipla e relidos antes de executar. Não usar a área de transferência: o `SetClipboardData` falhou com "Identificador inválido".
- Na execução efetiva aparece o aviso FG013 ("Consulta de segurança"), que se passa com Enter.
- O SAP pode pedir "um script está tentando acessar o SAP GUI"; isso é normal.
- Arquivos na pasta do relatório (padrão `\\brsvp0000009\Groups\dfg\Financeiro\Tesouraria\25 Gestão de Caixa\15. MELHORIAS\FUNDO FIXO`, configurável em `config.ini`; no VBS o "ã" é escrito como `ChrW(227)`): `fundo_fixo.txt`, `a_compensar.csv`, `historico_compensacoes.csv`. Na pasta do app: `logs/app.log` e `logs/f13_*.csv`.

## O que já foi validado no SAP real
- Extração da FBL3H pelo VBS.
- F.13 em teste e uma compensação efetiva manual da loja 04018 (feita por mim, pela F.13).
- Digitação na seleção múltipla com até 7 documentos por loja, em modo teste.

## Pendências e pontos de atenção
- Validar a primeira compensação efetiva pelo aplicativo, com 2 ou 3 lojas. Conferir se o doc. de compensação capturado (heurística na tela de saída da F.13, função `docs_compensacao`) bate com o SAP.
- Seleção múltipla com mais de 8 documentos: no SAP real, com 10 documentos, a conferência acusou "esperados 10, lidos 9" (faltava o 8º). Causa: pedir a posição 8 da rolagem parava na 7 e o 9º era escrito por cima do 8º. Corrigido em `_ir_para` (relê a posição real; se não alcançar, aperta Enter; se ainda assim não alcançar, para com erro) e coberto por `tests/test_selecao_multipla.py` com uma tabela falsa. **Falta validar no SAP**, em modo teste, numa loja com mais de 8 documentos.
- O exercício da F.13 é fixo no ano corrente: em janeiro, documentos lançados em dezembro não seriam selecionados.
- Na virada do mês, lançamentos retroativos com data DOC do mês anterior ficam fora do corte.
- Próximo passo proposto (não implementado):
  - ao abrir, montar sozinho o lote padrão (todas as prontas) e rodar o teste automaticamente;
  - a analista escolhe entre Compensar lote e Editar lote;
  - editar o lote refaz o teste só das lojas alteradas.
- Fora de escopo: outras contas, correção das partidas antigas sem par (plano de ação até 30/10), ajustes de valor do fundo, integração via RFC.

## Como testar sem SAP
- `py -m unittest discover -s tests -v` roda os testes das regras de negócio (`tests/test_regras.py`) e da seleção múltipla com uma tabela SAP falsa (`tests/test_selecao_multipla.py`). Só usa a biblioteca padrão; rode antes de todo commit. Toda mudança de regra ganha ou ajusta um teste.
- `exemplos/fbl3h_ficticio.txt` tem 13 lojas fictícias (09101 a 09113), uma em cada situação. `exemplos/gerar_ficticio.py` recria o arquivo.
- `py analisar.py exemplos/fbl3h_ficticio.txt --mes 2026-10 --demo` gera a página estática de demonstração.
- Para testar o app sem SAP, substitua `rodar_relatorio`, `sessao_sap` e `f13_loja` por versões falsas e rode `app()`.

## Cuidados
- Nunca commitar extrações reais do SAP: o `.gitignore` bloqueia `.txt` e `.csv`, exceto o exemplo.
- Não remover nenhuma trava de segurança sem a minha confirmação explícita.
- Ao mudar regras de negócio, atualize este arquivo, o README e `docs/fluxo.html`.
- Mantenha o Intent Layer em dia: ao criar uma pasta com responsabilidade própria ou descobrir um contrato escondido, anote-o no `CLAUDE.md` mais próximo (ou crie um nó na pasta). Cada nó deve ficar com menos de ~4 mil tokens.

## Padrões de código
- **Sem dependências novas.** Só a biblioteca padrão do Python, mais `pywin32` e `pywebview`. Instalar algo no computador da empresa é difícil; pergunte antes.
- **Nomes e mensagens em português**, no estilo atual: funções curtas com verbo (`ler_lista`, `salvar_lista`), constantes em MAIÚSCULAS no topo de `fundo_fixo.py`. Comentários só onde a regra não é óbvia, e citando a regra.
- **Erros para a analista:** levantar `Falha("mensagem clara")`, dizendo o que fazer. Para falhas internas, `RuntimeError`. Nunca engolir uma exceção num trecho que decide se algo é compensado.
- **Registro:** toda ação relevante passa por `log()`, que vai para a tela e para `logs/app.log`.
- **Caminhos:** só via constantes (`PASTA_RELATORIO`, `PASTA_LOG`…) e `config.ini`. Nada de caminho fixo espalhado pelo código.
- **Codificação:** `.py`, `.html` e `.md` em UTF-8. Arquivos `.vbs` em Windows-1252: prefira ASCII e use `ChrW()` para acentos em valores. CSVs gravados em `utf-8-sig` com `;` para abrir certo no Excel.
- **Regra do par em dois lugares:** `analisar.analisar` (tela) e `fundo_fixo.par_valido`/`validar_com_relatorio` (antes da F.13). Mudou um, mude o outro; os testes cobrem os dois.
- **SAP GUI:** IDs de tela só vindos de gravação real da Vah. Depois de digitar no SAP, reler e conferir antes de executar (como `conferir_selecao`). Código novo que toca o SAP roda primeiro com `teste=True`.
- **Mudanças pequenas e focadas**, sem reformatar arquivos inteiros nem refatorar o que não foi pedido.

## Fluxo de trabalho
- Antes de commitar: rodar os testes e a skill `/revisar` (checklist do projeto). Para mudanças grandes, também `/code-review`; se mexer em arquivos, caminhos ou entrada de dados, `/security-review`.
- Commits em português, no imperativo e curtos ("Troca a pasta padrão pela rede").
- Diga sempre o que foi testado só sem SAP e o que ainda precisa ser validado no SAP real.
