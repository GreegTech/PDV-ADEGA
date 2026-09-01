# Adega Torres — ERP SaaS

ERP web multi-tenant para adegas, iniciado a partir do PDV da Adega Torres.

## Stack
- FastAPI
- PostgreSQL 16
- SQLAlchemy
- JWT + Argon2
- Docker Compose
- Nginx

## Recursos atuais
- isolamento de dados por empresa e loja
- empresas, lojas, usuários, perfis e permissões
- troca segura de empresa/loja com novo token de acesso
- painel administrativo em `/admin.html`
- cadastro empresarial de produto com saldo, custo, preço e estoque mínimo por loja
- transferências atômicas entre lojas com dupla movimentação auditável
- abertura e fechamento de caixa por loja, terminal e operador
- sangria, suprimento, conferência e diferença de fechamento
- vendas obrigatoriamente vinculadas a uma sessão de caixa aberta
- autenticação de usuário
- cadastro, edição, ativação e desativação de produtos
- consulta de GTIN/EAN com preenchimento automático pelo catálogo
- estoque persistido no PostgreSQL
- compras/entradas com custo médio ponderado (CMP)
- importação e conciliação de NF-e
- movimentações auditáveis de estoque
- registro de vendas e baixa automática de estoque
- preço de tabela e histórico de alterações
- descontos por item em R$ ou percentual
- limite de desconto por perfil
- preço, desconto, preço efetivo e CMV congelados em cada item vendido
- dashboard com vendas líquidas, descontos, CMV e margem bruta

## Blocos consolidados

- **Bloco 1:** fornecedores, compras/entradas, CMP e NF-e.
- **Bloco 2:** preço, descontos, CMV, histórico de preço e ciclo de vida seguro do produto.
- **ERP SaaS — Fase 1:** fundação multi-tenant, empresas, lojas, usuários e permissões.
- **ERP SaaS — Fase 2:** inventário multi-loja, transferências e caixa operacional.

Detalhes do Bloco 2: `docs/bloco2-consolidado.md`.
Roadmap do ERP SaaS: `docs/ROADMAP_SAAS.md`.

## Executar

1. Copie `.env.example` para `.env`.
2. Troque todas as senhas e chaves.
3. Ajuste os limites de desconto por perfil, se necessário.
4. Execute:

```bash
docker compose up -d --build
```

Na primeira inicialização, a API importa `backend/data/catalogo_produtos_adega_torres.csv`
para a tabela auxiliar `catalog_products`. Ao bipar um código em **Novo produto**, o
sistema consulta primeiro os produtos cadastrados e depois esse catálogo.

Acessos:
- Frontend: `http://IP-DO-SERVIDOR:8082`
- Caixa: `http://IP-DO-SERVIDOR:8082/caixa.html`
- Transferências: `http://IP-DO-SERVIDOR:8082/transferencias.html`
- Administração: `http://IP-DO-SERVIDOR:8082/admin.html`
- Swagger/API: `http://IP-DO-SERVIDOR:8000/docs`
- Health: `http://IP-DO-SERVIDOR:8000/health`

## Primeiro login
Use `ADMIN_USER` e `ADMIN_PASSWORD` definidos no `.env`.

> Nunca envie o arquivo `.env` real para o GitHub.
