# Documentação para pessoas

## Propósito
Páginas estáticas para a Vah e quem ela mostrar o processo: o fluxo ilustrado e uma demonstração da tela com dados fictícios. Não fazem parte do app e não são lidas pelo código.

## Entradas
- `fluxo.html`: escrito à mão. Diagrama em raias do processo, travas de segurança e arquivos usados. Tema claro/escuro por variáveis CSS em `:root`.
- `demonstracao.html`: **gerado**, não editar à mão. É `modelo_revisao.html` com os dados de `exemplos/fbl3h_ficticio.txt` e `"demo": true`.

## Contratos e invariantes
- Mudou regra de negócio, trava ou nome de arquivo: `fluxo.html` precisa contar a mesma história que o CLAUDE.md da raiz e o README.
- Mudou `modelo_revisao.html`, `analisar.py` ou os exemplos: gere a demonstração de novo, na pasta do projeto:
  1. `py analisar.py exemplos/fbl3h_ficticio.txt --mes 2026-10 --demo --saida <pasta temporária>`
  2. copie `<pasta temporária>/revisao_compensacao.html` por cima de `docs/demonstracao.html`.
  A única diferença esperada em relação à versão anterior é `gerado_em` (e o que você mudou de propósito).
- A demonstração usa só dados fictícios. Nunca gerar a partir de uma extração real.

## Anti-padrões
- Editar `demonstracao.html` direto (a próxima geração apaga a mudança).
- Gerar com `--saida docs`: deixa `analise.json` e `revisao_compensacao.html` soltos aqui. Gere numa pasta temporária e copie só a página.

## Relacionados
- Tela original: `../modelo_revisao.html`
- Dados: `../exemplos/CLAUDE.md`
