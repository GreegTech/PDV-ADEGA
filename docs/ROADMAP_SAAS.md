# Roadmap — Adega ERP SaaS

## Princípio de arquitetura

Cada operação autenticada possui um contexto obrigatório de `empresa + loja`.
Produtos operacionais, compras, vendas e movimentações são filtrados nesse contexto.
O catálogo GTIN é global e compartilhado, mas os dados comerciais e o estoque nunca são.

## Fase 1 — Multi-tenant e controle de acesso

Status: implementada.

- empresas e primeira loja no onboarding;
- múltiplas lojas por empresa;
- usuários globais vinculados a empresas por `membership`;
- acesso a todas as lojas ou a lojas selecionadas;
- perfis Administrador, Gerente e Operador;
- permissões granulares persistidas no banco;
- empresa e loja gravadas no JWT;
- troca de contexto com reemissão do JWT;
- isolamento de produtos, fornecedores, compras, vendas e movimentações;
- migração automática dos dados existentes para Adega Torres / Loja Principal;
- painel administrativo web;
- testes de unicidade por tenant, permissões e acesso restrito a lojas.

## Fase 2 — Operação multi-loja

Status: implementada na versão 1.1.0.

- cadastro comercial único do produto por empresa;
- inventário por `produto + loja`, com saldo, custo médio, preço e estoque mínimo;
- consolidação automática de produtos repetidos da Fase 1 sem perder históricos;
- transferências atômicas entre lojas com saída e entrada auditáveis;
- abertura e fechamento de caixa por loja, terminal e operador;
- suprimento, sangria, valor esperado e diferença de fechamento;
- vendas vinculadas ao caixa aberto e separadas por forma de pagamento;
- compras e NF-e atualizando o inventário da loja ativa;
- dashboard, movimentações e relatórios isolados por unidade.

## Fase 3 — Financeiro

- contas a pagar e receber;
- categorias, centros de custo e competência;
- conciliação com vendas, compras e fiado;
- fluxo de caixa realizado e projetado;
- DRE gerencial por loja e consolidada.

## Fase 4 — Comercial SaaS

- planos, limites e recursos contratados;
- trial e onboarding;
- assinaturas, cobranças e inadimplência;
- painel da plataforma com tenants, uso e saúde;
- bloqueio controlado sem perda de dados.

## Fase 5 — Ecossistema

- catálogo global enriquecido;
- integrações fiscais;
- WhatsApp para atendimento e campanhas autorizadas;
- delivery, pedidos e acompanhamento.

## Fase 6 — BI, IA e automação

- painéis comparativos por loja e período;
- previsão de ruptura e excesso de estoque;
- sugestão de compra por giro, prazo e sazonalidade;
- automações com aprovação humana e trilha de auditoria.

## Ordem de implementação

Uma fase só avança quando as migrações são reversíveis, o isolamento tenant está coberto
por testes e os fluxos já existentes continuam funcionando. A Fase 2 deve começar pela
normalização de inventário; caixa e transferências dependem dessa base.
