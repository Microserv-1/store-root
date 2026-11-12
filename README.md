# Microserv Store

> **Atualização de 12/11:** a Pessoa B publicou as correções do handoff com sua própria autoria. Os novos commits estão sendo revalidados na integração e no Jenkins. Consulte [HANDOFF-PESSOA-B.md](HANDOFF-PESSOA-B.md) para o roteiro original e os relatórios para as versões efetivamente testadas. Não criar commits da Pessoa A nos repositórios de B.

Projeto acadêmico de Platforms, Microservices, DevOps and APIs — 2026.

Pessoa A: Account (Python/FastAPI), Auth (Java/Spring Boot), Gateway (Go), infraestrutura, observabilidade e balanceamento. Product, Order e Exchange Python da Pessoa B estão incorporados como submódulos, com Redis, RabbitMQ e bancos próprios na execução integrada.

## Executar localmente

Pré-requisitos: Git, Docker Compose e Python 3.10+. Java 21 e Go são compilados nos containers.

```powershell
git clone --recurse-submodules https://github.com/Microserv-1/store-root.git
cd store-root
python scripts/setup-local.py
docker compose up --build -d
python tests/smoke.py
```

Para o projeto completo, incluindo as entregas da Pessoa B:

```powershell
python scripts/setup-local.py
docker compose -f compose.yaml -f compose.business.yaml up --build -d
python tests/smoke.py
python tests/business_integration.py
```

`tests/business_resilience.py` executa indisponibilidades controladas de Redis/RabbitMQ **locais** e os reinicia ao final. Ele não deve ser usado contra ambientes compartilhados. `setup-local.py` acrescenta segredos ausentes sem substituir os existentes.

Gateway: http://localhost:8080. Apenas ele publica portas de aplicação. O PostgreSQL persiste no volume `account-data`; os segredos locais são gerados em `.env`, ignorado pelo Git.

```powershell
docker compose --profile monitoring up -d
python scripts/load.py --users 4 --duration 60 --scenario identity
```

Prometheus: http://localhost:9090. Grafana: http://localhost:3000, usuário `admin`, senha no campo `GRAFANA_PASSWORD` do `.env`. As interfaces administrativas ficam vinculadas ao loopback.

## Kubernetes e deploy

Jenkins local: [instalação, credenciais e execução dos jobs](docs/site/docs/jenkins.md). As imagens públicas usam `uyris/store-<serviço>:<SHA>` no Docker Hub. O parâmetro `DEPLOY` só deve ser habilitado depois de conferir o cluster associado à credencial `store-kubeconfig`.

Cada serviço tem Dockerfile, Jenkinsfile e `k8s/k8s.yaml`. Infraestrutura compartilhada em `infra/`; scripts em `scripts/`. Consulte [execução e deploy](docs/site/docs/deploy.md), [contratos para B](docs/site/docs/contracts.md) e [estado das verificações](docs/site/docs/status.md).

O deploy AWS cria recursos pagos e exige conta, permissões, revisão de região/custos e configuração de segredos. Nenhum template representa evidência de um deploy executado.

## Submódulos e autoria

Após alterar um serviço, publique seu commit no repositório correspondente e então atualize o ponteiro neste repositório. `git submodule update --init --recursive` recupera os commits registrados. Mudanças locais dentro de submódulos não são incluídas automaticamente por um commit na raiz.

Documentação individual e comum: [store-docs-a](https://github.com/Microserv-1/store-docs-a). Os contratos iniciais de Account/Auth/Gateway precisam ser confrontados com os enunciados oficiais, ainda não fornecidos.

Resultados locais e vídeo técnico: [estado e evidências](docs/site/docs/status.md). Os commits e ponteiros dos submódulos foram publicados, e o clone recursivo direto do GitHub foi validado com acesso aos repositórios privados. O teste `scripts/verify-local-clone.py` também permite validar a estrutura usando URLs locais apenas no clone de verificação.
