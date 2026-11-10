# Microserv Store

Projeto acadêmico de Platforms, Microservices, DevOps and APIs — 2026.2.

- **Pessoa A (Yuri Henrique)**: Account (Python/FastAPI), Auth (Java/Spring Boot), Gateway (Go), infraestrutura base, observabilidade e balanceamento.
- **Pessoa B (Gustavo Lima Affonso Ferreira)**: Product (Python/FastAPI + Cache Redis), Order (Python/FastAPI + Mensageria RabbitMQ), Exchange (Python/FastAPI + APIs externas de câmbio com fallback), integração ponta a ponta, testes de gargalos e documentação da Pessoa B.

## Executar localmente (Docker Compose — 6 microsserviços + Postgres + Redis + RabbitMQ)

Pré-requisitos: Git, Docker Compose e Python 3.10+. Java 21, Go e Python 3.12 são compilados nos containers.

```bash
git clone --recurse-submodules https://github.com/Microserv-1/store-root.git
cd store-root
python3 scripts/setup-local.py
docker compose --profile monitoring up --build -d
python3 tests/smoke.py
python3 tests/cache_bottleneck.py
python3 tests/messaging_bottleneck.py
```

Gateway: `http://localhost:8080`. Apenas ele publica portas de aplicação. O PostgreSQL persiste no volume `account-data`, o Redis no volume `redis-data` e o RabbitMQ no volume `rabbitmq-data`; os segredos locais são gerados em `.env`, ignorado pelo Git.

```bash
python3 scripts/load.py --users 8 --duration 30 --scenario products_cached --output artifacts/load-products-cached.json
python3 scripts/load.py --users 8 --duration 30 --scenario products_uncached --output artifacts/load-products-uncached.json
python3 scripts/load.py --users 8 --duration 30 --scenario business_mix --output artifacts/load-business-mix.json
```

Prometheus: `http://localhost:9090`. Grafana: `http://localhost:3000`, usuário `admin`, senha no campo `GRAFANA_PASSWORD` do `.env`. As interfaces administrativas ficam vinculadas ao loopback.

## Kubernetes e deploy

Cada um dos 6 serviços tem `Dockerfile`, `Jenkinsfile` e `k8s/k8s.yaml` (com Deployment 2 réplicas, Service ClusterIP, HPA 2..5 em 60% de CPU e PDB). Infraestrutura compartilhada em `infra/`; scripts em `scripts/`. Consulte:
- Documentação Pessoa A: [store-docs-a](https://github.com/Microserv-1/store-docs-a) (`docs/site`)
- Documentação Pessoa B: [store-docs-b](https://github.com/Microserv-1/store-docs-b) (`docs/site-b`)

O deploy AWS cria recursos pagos e exige conta, permissões, revisão de região/custos e configuração de segredos. Nenhum template representa evidência de um deploy executado.

## Submódulos e autoria

Após alterar um serviço, publique seu commit no repositório correspondente e então atualize o ponteiro neste repositório. `git submodule update --init --recursive` recupera os commits registrados. Mudanças locais dentro de submódulos não são incluídas automaticamente por um commit na raiz.
