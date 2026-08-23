# Adega Torres — PDV

MVP web para gestão da Adega Torres.

## Stack
- FastAPI
- PostgreSQL 16
- SQLAlchemy
- JWT + Argon2
- Docker Compose
- Nginx

## Recursos atuais
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

Detalhes do Bloco 2: `docs/bloco2-consolidado.md`.

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
- Swagger/API: `http://IP-DO-SERVIDOR:8000/docs`
- Health: `http://IP-DO-SERVIDOR:8000/health`

## Primeiro login
Use `ADMIN_USER` e `ADMIN_PASSWORD` definidos no `.env`.

> Nunca envie o arquivo `.env` real para o GitHub.
