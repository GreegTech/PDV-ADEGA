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
- cadastro e consulta de produtos
- consulta de GTIN/EAN com preenchimento automático pelo catálogo
- estoque persistido no PostgreSQL
- ajuste/movimentação de estoque
- registro de vendas e itens
- baixa automática de estoque
- dashboard básico

## Executar

1. Copie `.env.example` para `.env`.
2. Troque todas as senhas e chaves.
3. Execute:

```bash
docker compose up -d --build
```

Na primeira inicialização, a API importa `backend/data/catalogo_produtos_adega_torres.csv`
para a tabela auxiliar `catalog_products`. Ao bipar um código em **Novo produto**, o
sistema consulta primeiro os produtos cadastrados e depois esse catálogo. A quantidade
comprada gera uma movimentação `ENTRADA_INICIAL` junto com o cadastro.

Acessos:
- Frontend: `http://IP-DO-SERVIDOR:8082`
- Swagger/API: `http://IP-DO-SERVIDOR:8000/docs`
- Health: `http://IP-DO-SERVIDOR:8000/health`

## Primeiro login
Use `ADMIN_USER` e `ADMIN_PASSWORD` definidos no `.env`.

> Nunca envie o arquivo `.env` real para o GitHub.
