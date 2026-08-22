# Bloco 1 — Fornecedores, compras e CMP

## Regra de custo
`products.cost` passa a representar o custo médio ponderado móvel atual (CMP).

Ao registrar uma compra:

`novo_cmp = ((estoque_anterior * cmp_anterior) + (quantidade_entrada * custo_entrada)) / estoque_novo`

O resultado monetário é arredondado para 2 casas decimais.

## Histórico imutável
Cada `purchase_item` preserva:
- quantidade;
- custo unitário efetivo da compra;
- custo total;
- estoque anterior;
- CMP anterior;
- estoque posterior;
- CMP posterior.

A movimentação de estoque referencia a compra responsável pela entrada.

## Regras
- Entrada comercial deve ocorrer por `POST /purchases`.
- Ajuste físico em `/stock/adjust` não recalcula custo médio.
- Venda continua congelando em `sale_items.unit_cost` o CMP existente no momento da venda.
- Alterar uma compra histórica não é parte do fluxo normal; correções futuras deverão ocorrer por estorno/ajuste auditado.

## Endpoints
- `GET /suppliers`
- `POST /suppliers`
- `GET /purchases`
- `POST /purchases`
