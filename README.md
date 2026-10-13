# Compensação do fundo fixo SAMS

Aplicativo local para revisar e compensar, no SAP, as partidas em aberto da conta de fundo fixo das lojas SAMS (empresa **BR21**, conta **28200202**).

Ele extrai a FBL3H, monta os pares débito/crédito por documento, mostra numa tela o que está pronto e o que precisa de decisão, e roda a **F.13** loja por loja depois da confirmação da analista. Cada documento de compensação fica registrado num histórico.

Veja o diagrama do processo em [`docs/fluxo.html`](docs/fluxo.html).

- `docs/fluxo.html`: diagrama do processo e travas de segurança.
- `docs/demonstracao.html`: a tela de revisão com dados fictícios (abre direto no navegador).

## Requisitos

- Windows, com **SAP GUI** aberto e logado e **scripting habilitado** (SAP Logon > Opções > Acessibilidade e scripting).
- **Python 3.8+** (o comando `py` precisa funcionar no Prompt de Comando).
- Pacotes: `pywin32` e `pywebview` (`requirements.txt`).
- Acesso à pasta onde o relatório é salvo (padrão: `Z:\15. MELHORIAS\FUNDO FIXO\temp`).

## Instalação

1. Baixe ou clone o repositório numa pasta do computador.
2. Dê duplo clique em **`Instalar (uma vez).bat`**, ou rode:
   ```
   py -m pip install --user -r requirements.txt
   ```
3. (Opcional) Copie `config.exemplo.ini` como `config.ini` para mudar pasta, empresa ou conta.

## Uso

Com o SAP aberto, dê duplo clique em **`Fundo Fixo.vbs`**. Nenhum terminal aparece.

1. A janela do aplicativo abre e extrai a FBL3H em segundo plano.
2. A tela de revisão mostra as lojas em três grupos: **Para decidir**, **Prontas** e **Sem movimento**. As prontas já vêm marcadas.
3. **Montar lote** salva o lote de compensação em `a_compensar.csv`.
4. **Testar lote** roda a F.13 em teste. **Compensar lote** pede confirmação e roda a F.13 efetiva.
5. O resultado aparece por loja, com o documento de compensação. O botão **Histórico** mostra todas as compensações já feitas.

Fechar a janela encerra o aplicativo (ela não fecha com a F.13 rodando). Se o SAP perguntar se um script pode acessar o SAP GUI, clique em OK.

### Linha de comando (alternativa)

```
py fundo_fixo.py app                      # o mesmo que o .vbs
py fundo_fixo.py compensar                # dry run com a_compensar.csv
py fundo_fixo.py compensar --efetivo      # compensação real (pede COMPENSAR)
py fundo_fixo.py diagnostico              # grava os campos da seleção múltipla da F.13
py analisar.py exportacao.txt --mes 2026-10   # só a análise, gera a página estática
```

## Regras de negócio

**Análise**
- A partida inicial (tipo **SE** ou **AB**) é o fundo de referência da loja e nunca é compensada.
- Só entram partidas com **data DOC no mês corrente** em diante.
- O par é definido pelo **nº do documento dentro da mesma loja (atribuição)**: exatamente **1 débito e 1 crédito**, que somam zero e têm a **mesma data DOC**. Lançamento de outra loja nunca é contrapartida.
- Crédito = valor negativo (chave 50); débito = valor positivo (chave 40).
- Só tipo **BC** entra; outros tipos vão para revisão.

**Classificação das lojas**
- **Erro**: documento sem par, com mais de 2 linhas ou com datas diferentes (fica bloqueado).
- **Revisar**: lançamento não BC, valores diferentes entre os pares, valor diferente do fundo de referência ou dois fechamentos na mesma data DOC.
- **Pronta**: todos os pares válidos. **Sem movimento**: nada em aberto no mês.

**Antes e durante a F.13**
- O lote só é montado com saldo da seleção = 0,00.
- A FBL3H é extraída de novo e cada documento é conferido outra vez; se qualquer um falhar, nada é executado.
- Um documento cujo número também aparece em outra loja fica bloqueado: a F.13 seleciona por número e incluiria esse lançamento.
- Uma execução da F.13 por loja (um documento de compensação por loja). O aplicativo digita os documentos na seleção múltipla e relê a tela antes de executar.
- Depois da efetiva, confere na FBL3H se as partidas saíram do aberto.

## Arquivos gerados

| Arquivo | Onde | Conteúdo |
|---|---|---|
| `fundo_fixo.txt` | pasta do relatório | Extração da FBL3H |
| `a_compensar.csv` | pasta do relatório | Lote de compensação (loja; documento; data DOC; valor) |
| `historico_compensacoes.csv` | pasta do relatório | Uma linha por compensação efetiva, com o doc. de compensação |
| `logs/app.log` | pasta do aplicativo | Registro de tudo o que aconteceu |
| `logs/f13_*.csv` | pasta do aplicativo | Log de cada execução (teste ou efetiva) |

## Estrutura

```
fundo_fixo.py          aplicativo: servidor local, janela, SAP (FBL3H e F.13), histórico
analisar.py            regras de negócio: leitura da FBL3H, pares e classificação das lojas
modelo_revisao.html    tela de revisão (recebe os dados da análise)
relatorio_fbl3h.vbs    script do SAP GUI que exporta a FBL3H
Fundo Fixo.vbs         atalho que abre o aplicativo sem terminal
docs/                  fluxo e demonstração
exemplos/              exportação fictícia para testes (gerar_ficticio.py recria)
```

## Pontos ainda a validar

- O número do documento de compensação é lido da tela de saída da F.13; confirmar na primeira compensação real.
- Rolagem da seleção múltipla com mais de 8 documentos por loja ainda não foi testada no SAP.
- O exercício usado na F.13 é o ano corrente (em janeiro, documentos lançados em dezembro não seriam selecionados).
- Lançamentos retroativos com data DOC do mês anterior ficam fora do corte do mês.

## Segurança

O repositório não deve conter extrações reais do SAP: o `.gitignore` bloqueia `*.txt` e `*.csv` (exceto o exemplo fictício). Como o código descreve um processo interno, prefira um repositório **privado**.
