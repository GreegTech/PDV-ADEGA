# Bloco 2 — Preço, descontos e CMV

Status: **consolidado**.

## Preço de tabela

- `products.price` representa apenas o preço de tabela atual.
- Alterar o preço não modifica vendas antigas.
- Cada alteração manual de preço gera um registro em `product_price_history` com preço anterior, novo preço, usuário e data/hora.
- O histórico pode ser consultado diretamente no editor do produto.

## Venda e snapshot financeiro

Cada `sale_item` congela no momento da venda:

- `list_unit_price`: preço de tabela usado na venda;
- `discount_unit`: desconto unitário concedido;
- `effective_unit_price`: preço unitário efetivamente cobrado;
- `unit_cost`: CMP vigente no momento da venda;
- `gross_total`: valor bruto da linha;
- `discount_total`: desconto total da linha;
- `net_total`: valor líquido da linha;
- `cmv_total`: CMV total da linha.

A venda também congela `gross_total`, `discount_total`, `total`, `cmv_total` e `gross_margin`.

## Descontos

- O carrinho aceita desconto por item em R$ ou percentual.
- O backend sempre recalcula usando o preço de tabela armazenado no banco; o frontend não pode forjar preço ou custo.
- Desconto nunca pode ultrapassar o preço do item.
- Existe limite máximo por perfil, configurável por ambiente:
  - `MAX_DISCOUNT_OPERATOR_PERCENT` — padrão 10%;
  - `MAX_DISCOUNT_MANAGER_PERCENT` — padrão 20%;
  - `MAX_DISCOUNT_ADMIN_PERCENT` — padrão 100%.
- A API expõe a política efetiva em `GET /sales/discount-policy` e o frontend limita o campo de desconto de acordo com o perfil.

## CMV e margem

- `products.cost` é o custo médio ponderado atual.
- Compras/NF-e atualizam o CMP.
- Movimentações físicas manuais não alteram o CMP.
- A venda congela o custo atual em `sale_items.unit_cost`.
- Mudanças futuras de custo não recalculam o CMV de vendas antigas.

## Ciclo de vida do produto

- Produto ativo aparece no PDV.
- Produto desativado não pode ser vendido e some do carrinho/busca do PDV.
- Produto desativado preserva compras, vendas, CMV e movimentações antigas.
- Pode ser reativado posteriormente.
- Exclusão definitiva só é permitida quando estoque = 0 e não existe histórico de venda, compra ou movimentação.

## Fora do Bloco 2

Os itens abaixo ficam para os próximos blocos porque exigem entidades financeiras próprias:

- clientes;
- fiado / contas a receber;
- pagamentos parciais;
- abertura e fechamento de caixa;
- recebimento posterior de vendas antigas.

Essas funcionalidades não devem alterar a lógica histórica consolidada neste bloco.
