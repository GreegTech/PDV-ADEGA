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

Acessos:
- Frontend: `http://IP-DO-SERVIDOR:8080`
- Swagger/API: `http://IP-DO-SERVIDOR:8000/docs`
- Health: `http://IP-DO-SERVIDOR:8000/health`

## Primeiro login
Use `ADMIN_USER` e `ADMIN_PASSWORD` definidos no `.env`.

> Nunca envie o arquivo `.env` real para o GitHub.
