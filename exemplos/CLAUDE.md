# Exemplos fictícios

## Propósito
Dados falsos, no mesmo layout da FBL3H, para testar sem SAP. Não contém e nunca deve conter dado real.

## Entradas
- `gerar_ficticio.py`: recria `fbl3h_ficticio.txt`. Rode **dentro desta pasta** (`py gerar_ficticio.py`), porque ele grava no diretório atual.
- `fbl3h_ficticio.txt`: 13 lojas (09101 a 09113), em outubro/2026, uma situação por loja. É o único `.txt` liberado no `.gitignore`.

## Contratos e invariantes
- Cada loja é um cenário de regra: 09101–09106 prontas; 09107 erro (só crédito); 09108 revisar (duas datas DOC iguais); 09109 revisar (lançamento SA e troca de valor do fundo); 09110 pronta com dias faltando; 09111 sem movimento; 09112 abertura AB e débito antigo; 09113 retroativo de 30/09.
- `tests/test_regras.py` (classe `ExemploFicticio`) e `docs/demonstracao.html` dependem destes dados. Mudar o gerador muda os dois: rode os testes e gere a demonstração de novo (veja `docs/CLAUDE.md`).
- Os números de documento são sequenciais a partir de 1399000101; os testes não fixam números, só status e cenários.
- Mês de referência é sempre `--mes 2026-10`; sem ele, a análise usa o mês atual e quase tudo vira "antigo".

## Padrões
Para cobrir uma regra nova: acrescente uma loja nova (09114 em diante) com a situação, em vez de alterar uma existente. Depois atualize o status esperado no teste e a lista acima.

## Anti-padrões
- Nunca copiar uma extração real para cá, nem "anonimizada".
- Não usar lojas reais (códigos 04xxx etc.); os fictícios são 091xx.
