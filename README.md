# Lab App

## Rodar localmente (Docker Compose)

    docker compose up --build                      # http://localhost:8080
    docker compose up --build --scale backend=2    # 2 réplicas do back (botão "Qual servidor?" mostra os dois)
    docker compose down                            # para tudo, mantém os dados do Redis
    docker compose down -v                         # para tudo e apaga os dados

Desenvolvimento com recarga automática:

    docker compose -f compose.yaml -f compose.dev.yaml up redis backend
    cd frontend && npm run dev                     # http://localhost:5173 (proxy /api -> :8000)

Ver os dados:

    docker compose exec redis redis-cli
    > ZREVRANGE items:by_date 0 -1

## Deploy no AWS Learner Lab

1. Inicie o lab e copie as credenciais (AWS Details) para ~/.aws/credentials.
2. Build e push das imagens (Docker Hub), sempre com tag nova:
   docker build --platform linux/amd64 -t USUARIO/lab-backend:v5  ./backend  && docker push USUARIO/lab-backend:v5
   docker build --platform linux/amd64 -t USUARIO/lab-frontend:v4 ./frontend && docker push USUARIO/lab-frontend:v4
3. cd terraform && cp terraform.tfvars.example terraform.tfvars (edite as imagens)
4. terraform init && terraform apply
5. Abra o output alb_url.
6. Ao terminar: terraform destroy
