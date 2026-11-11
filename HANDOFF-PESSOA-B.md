# Handoff para Pessoa B — mudanças a implementar

Data: 11/11/2026. Este documento substitui os commits de integração feitos por Yuri nos repositórios da Pessoa B. Os patches abaixo são referências de implementação e foram preservados antes do rollback. A Pessoa B deve revisar, entender, implementar e testar as alterações e registrar seus próprios commits, com divulgação do auxílio de IA na documentação. Não alterar a autoria dos commits de outra pessoa.

## 1. Estado após o rollback

| Repositório | `main` restaurado para | Commit de Yuri retirado de `main` |
|---|---|---|
| `Microserv-1/store-product` | `7daad6f862ab12f8955306293dd6b78d6a1de8d5` | `0d47017ef0ff267a08fee6b5c7b6ae0be47d89fd` |
| `Microserv-1/store-order` | `d0a05a5b6c4c8e4b24f5fcfdeb3a060523e90688` | `39fa88b931d89ae88db8f6e91dde38c1fa211efe` |
| `Microserv-1/store-exchange` | `e353943bdcfabddb475e799786005f275d24b086` | Nenhum commit de Yuri foi criado |

O histórico remoto de `main` foi recuado, pois um commit de revert manteria a autoria que precisava ser removida. Quem já recebeu os commits retirados deve alinhar a cópia local antes de voltar a publicar. Não fazer `git pull`/merge que reincorpore esses commits, nem cherry-pick deles, pois isso mantém sua autoria original.

Antes de alinhar: salvar trabalho local não publicado em uma branch própria. Somente com o diretório limpo e sem trabalho que precise preservar, executar dentro de cada repositório:

```bash
git fetch origin
git switch main
git reset --hard origin/main
```

Esse reset descarta alterações locais: não executá-lo sem preservar o trabalho da própria pessoa. Usar a identidade Git real da Pessoa B nos commits novos. O reset de `main` não equivale a apagar permanentemente todos os objetos ou caches históricos do GitHub.

## 2. Mudanças obrigatórias em Product

Arquivo: `k8s/k8s.yaml`. O código Python de Product não foi modificado nesta rodada.

1. Remover `REDIS_URL` do ConfigMap; a URL contém senha e deve vir de Secret.
2. Trocar a chave de Secret de `DATABASE_URL` para `PRODUCT_DATABASE_URL`, mantendo o nome da variável de ambiente da aplicação como `DATABASE_URL`.
3. Adicionar variável `REDIS_URL` via `store-secrets`, chave `REDIS_URL`.
4. Configurar no Pod `dnsConfig.options`: `timeout=1` e `attempts=1`. O resolver padrão, quando o container Redis era parado, podia consumir o prazo do Gateway antes do fallback para PostgreSQL. Validar novamente no ambiente AWS.

Preservar as rotas e o suporte `?cache=bypass` já implementados por B. O Gateway de A já permite também `X-Cache-Control: no-cache`. Não confiar em `X-Account-ID` como substituto da validação JWT.

### Patch completo de Product

```diff
diff --git a/k8s/k8s.yaml b/k8s/k8s.yaml
index 50befa0..002c7e0 100644
--- a/k8s/k8s.yaml
+++ b/k8s/k8s.yaml
@@ -5,7 +5,6 @@ metadata:
   namespace: store
 data:
   SERVICE_NAME: product
-  REDIS_URL: redis://redis:6379/0
   CACHE_TTL_SECONDS: "120"
   CACHE_ENABLED: "true"
 ---
@@ -29,6 +28,8 @@ spec:
         prometheus.io/port: "8000"
         prometheus.io/path: /metrics
     spec:
+      dnsConfig:
+        options: [{name: timeout, value: '1'}, {name: attempts, value: '1'}]
       automountServiceAccountToken: false
       securityContext:
         runAsNonRoot: true
@@ -47,7 +48,10 @@ spec:
             secretKeyRef: {name: store-secrets, key: JWT_SECRET}
         - name: DATABASE_URL
           valueFrom:
-            secretKeyRef: {name: store-secrets, key: DATABASE_URL}
+            secretKeyRef: {name: store-secrets, key: PRODUCT_DATABASE_URL}
+        - name: REDIS_URL
+          valueFrom:
+            secretKeyRef: {name: store-secrets, key: REDIS_URL}
         resources:
           requests: {cpu: 100m, memory: 128Mi}
           limits: {cpu: "1", memory: 256Mi}
```

## 3. Mudanças obrigatórias em Order

### `app/main.py`: entrega pelo menos uma vez e idempotência

1. Adicionar `consume_one(queue, processor)` às duas implementações de broker.
2. No RabbitMQ, usar `basic_get(auto_ack=False)` e executar o processamento **antes** do ACK. `process_single_event_message` grava a notificação no banco; somente depois desse retorno enviar `basic_ack`.
3. Se o processamento falhar, enviar `basic_nack(requeue=True)` e propagar o erro. Fechar a conexão em `finally`. Se a conexão cair antes do ACK, a entrega permanece recuperável pelo broker.
4. No broker de memória dos testes, devolver a mensagem à fila quando o processamento falhar.
5. Na publicação, usar `confirm_delivery()` e `basic_publish(..., mandatory=True)`. A outbox só pode marcar publicação concluída quando a chamada não tiver falhado. Falha após publicação e antes do commit da outbox pode causar duplicata: o consumidor idempotente continua necessário.
6. No tratamento de payload inválido, uma falha ao publicar na DLQ não deve ser ignorada; deixar o erro propagar para que a mensagem original não seja confirmada e perdida.
7. Alterar `drain_queue_once` para chamar `consume_one(..., process_single_event_message)` e contar apenas mensagens efetivamente processadas. Remover o consumo RabbitMQ que confirma a mensagem antes do processamento.

### `app/main.py`: controle global de demonstração

`POST /orders/events/consumer` pausa o consumidor global; um usuário comum não deve controlar isso por padrão. Retornar 404, sem alterar o estado, quando `ENABLE_DEMO_CONTROLS` não for explicitamente `true`. Habilitar apenas em demonstração controlada. O replay de eventos próprios continua protegido pela propriedade do pedido.

### `k8s/k8s.yaml`: isolamento e credenciais

1. Remover a URL com `guest:guest` do ConfigMap.
2. Usar `ORDER_DATABASE_URL` como chave do Secret para a variável `DATABASE_URL`.
3. Usar `RABBITMQ_URL` como chave do Secret para a variável de mesmo nome.
4. Configurar DNS com `timeout=1`, `attempts=1`; o mesmo problema de resolução com broker parado causou timeout em criação de pedido, embora a operação devesse persistir com outbox pendente.
5. Manter `ENABLE_DEMO_CONTROLS: "false"` no ConfigMap.

### Testes e README

- Adicionar `tests/test_broker_reliability.py`: falha simulada de commit não gera ACK, gera NACK com requeue e fecha a conexão; sucesso só gera ACK depois do callback.
- Em `tests/test_order.py`, habilitar explicitamente o controle para o teste de demonstração já existente e acrescentar um teste de que, sem opt-in, a rota global retorna 404.
- Atualizar README com o contrato de entrega pelo menos uma vez, confirmações do broker, idempotência e configuração do modo de demonstração. Não prometer exatamente uma vez.

### Patch completo de Order, incluindo testes e README

```diff
diff --git a/README.md b/README.md
index 5320078..e87b9c1 100644
--- a/README.md
+++ b/README.md
@@ -17,6 +17,12 @@ Serviço de pedidos (`POST /orders`, `GET /orders`, `GET /orders/{id}`) em Pytho
 | `GET` | `/ready` | Público | Prontidão do banco e broker RabbitMQ |
 | `GET` | `/metrics` | Público (interno) | Métricas Prometheus |
 
+## Segurança e entrega de eventos
+
+O controle global `POST /orders/events/consumer` fica desabilitado por padrão (404). Para demonstração local controlada, habilitar explicitamente `ENABLE_DEMO_CONTROLS=true`; não habilitar em ambiente compartilhado com usuários reais. O replay de eventos continua restrito ao proprietário do pedido.
+
+A publicação usa confirmações do broker e `mandatory=True`. O consumidor confirma a entrega apenas após concluir a transação de notificação; falhas de processamento devolvem a mensagem à fila. O contrato é de entrega pelo menos uma vez, com consumidor idempotente, não de entrega exatamente uma vez.
+
 ## Regra de Conversão Monetária e Arredondamento
 
 - Todos os valores de pedidos e itens são persistidos no PostgreSQL em **USD** (`Numeric(12, 2)`).
diff --git a/app/main.py b/app/main.py
index 55d34e5..298c04b 100644
--- a/app/main.py
+++ b/app/main.py
@@ -120,6 +120,17 @@ class InMemoryBroker:
         with self._lock:
             return len(self._queues[queue])
 
+    def consume_one(self, queue: str, processor: Callable[[str], None]) -> bool:
+        raw = self.get_one(queue)
+        if raw is None:
+            return False
+        try:
+            processor(raw)
+        except Exception:
+            self.publish(queue, raw)
+            raise
+        return True
+
 
 class RabbitMQBroker:
     def __init__(self, url: str):
@@ -144,10 +155,12 @@ class RabbitMQBroker:
         conn, ch = self._connect()
         try:
             ch.queue_declare(queue=queue, durable=True)
+            ch.confirm_delivery()
             ch.basic_publish(
                 exchange="",
                 routing_key=queue,
                 body=body.encode("utf-8"),
+                mandatory=True,
                 properties=pika.BasicProperties(
                     delivery_mode=2,
                     content_type="application/json",
@@ -156,14 +169,19 @@ class RabbitMQBroker:
         finally:
             conn.close()
 
-    def get_one(self, queue: str) -> Optional[str]:
+    def consume_one(self, queue: str, processor: Callable[[str], None]) -> bool:
         conn, ch = self._connect()
         try:
             method_frame, _header_frame, body = ch.basic_get(queue=queue, auto_ack=False)
             if method_frame is None:
-                return None
+                return False
+            try:
+                processor(body.decode("utf-8"))
+            except Exception:
+                ch.basic_nack(delivery_tag=method_frame.delivery_tag, requeue=True)
+                raise
             ch.basic_ack(delivery_tag=method_frame.delivery_tag)
-            return body.decode("utf-8")
+            return True
         finally:
             conn.close()
 
@@ -254,11 +272,8 @@ def process_single_event_message(raw_message: str) -> None:
         total_usd = float(payload.get("total_usd", 0.0))
     except Exception as exc:
         logger.error(json.dumps({"service": "order", "event": "invalid_event_payload", "error": str(exc)}))
-        try:
-            broker.publish(ORDER_EVENTS_DLQ, raw_message)
-            EVENTS_DLQ.inc()
-        except Exception:
-            pass
+        broker.publish(ORDER_EVENTS_DLQ, raw_message)
+        EVENTS_DLQ.inc()
         return
 
     with Session() as session:
@@ -320,13 +335,12 @@ def drain_queue_once(max_messages: int = 50) -> int:
     processed = 0
     for _ in range(max_messages):
         try:
-            raw = broker.get_one(ORDER_EVENTS_QUEUE)
+            consumed = broker.consume_one(ORDER_EVENTS_QUEUE, process_single_event_message)
         except Exception as exc:
             logger.warning(json.dumps({"service": "order", "event": "broker_consume_error", "error": str(exc)}))
             break
-        if raw is None:
+        if not consumed:
             break
-        process_single_event_message(raw)
         processed += 1
     return processed
 
@@ -491,6 +505,8 @@ def get_events_summary(account_id: str = Depends(identity)):
 
 @app.post("/orders/events/consumer")
 def control_consumer(body: ConsumerControlIn, _account_id: str = Depends(identity)):
+    if os.environ.get("ENABLE_DEMO_CONTROLS", "false").lower() != "true":
+        raise HTTPException(404, "Demo controls disabled")
     state = set_consumer_enabled(body.enabled)
     processed = drain_queue_once() if state else 0
     return {"consumer_active": state, "drained_messages": processed}
diff --git a/k8s/k8s.yaml b/k8s/k8s.yaml
index b52450d..350eaa0 100644
--- a/k8s/k8s.yaml
+++ b/k8s/k8s.yaml
@@ -7,8 +7,8 @@ data:
   SERVICE_NAME: order
   PRODUCT_URL: http://product:8000
   EXCHANGE_URL: http://exchange:8000
-  RABBITMQ_URL: amqp://guest:guest@rabbitmq:5672/%2F
   ORDER_EVENTS_QUEUE: order.events
+  ENABLE_DEMO_CONTROLS: "false"
 ---
 apiVersion: apps/v1
 kind: Deployment
@@ -30,6 +30,8 @@ spec:
         prometheus.io/port: "8000"
         prometheus.io/path: /metrics
     spec:
+      dnsConfig:
+        options: [{name: timeout, value: '1'}, {name: attempts, value: '1'}]
       automountServiceAccountToken: false
       securityContext:
         runAsNonRoot: true
@@ -48,7 +50,10 @@ spec:
             secretKeyRef: {name: store-secrets, key: JWT_SECRET}
         - name: DATABASE_URL
           valueFrom:
-            secretKeyRef: {name: store-secrets, key: DATABASE_URL}
+            secretKeyRef: {name: store-secrets, key: ORDER_DATABASE_URL}
+        - name: RABBITMQ_URL
+          valueFrom:
+            secretKeyRef: {name: store-secrets, key: RABBITMQ_URL}
         resources:
           requests: {cpu: 100m, memory: 128Mi}
           limits: {cpu: "1", memory: 256Mi}
diff --git a/tests/test_broker_reliability.py b/tests/test_broker_reliability.py
new file mode 100644
index 0000000..d33a74d
--- /dev/null
+++ b/tests/test_broker_reliability.py
@@ -0,0 +1,45 @@
+import os
+from types import SimpleNamespace
+import pytest
+
+os.environ.setdefault("DATABASE_URL", "sqlite:///./test_order.db")
+os.environ.setdefault("JWT_SECRET", "order-unit-test-secret-with-32-plus-bytes!!")
+os.environ.setdefault("RABBITMQ_URL", "memory://local")
+from app.main import RabbitMQBroker
+
+class Channel:
+    def __init__(self):
+        self.acked = []
+        self.requeued = []
+
+    def basic_get(self, **kwargs):
+        return SimpleNamespace(delivery_tag=7), None, b'{"order_id":"fixture"}'
+
+    def basic_ack(self, delivery_tag):
+        self.acked.append(delivery_tag)
+
+    def basic_nack(self, delivery_tag, requeue):
+        self.requeued.append((delivery_tag, requeue))
+
+def test_ack_waits_for_successful_processing_and_failure_is_requeued():
+    channel = Channel()
+    closed = []
+    broker = RabbitMQBroker("amqp://unused")
+    broker._connect = lambda: (SimpleNamespace(close=lambda: closed.append(True)), channel)
+
+    def database_failure(raw):
+        assert channel.acked == []
+        raise RuntimeError("simulated database commit failure")
+
+    with pytest.raises(RuntimeError):
+        broker.consume_one("order.events", database_failure)
+    assert channel.acked == []
+    assert channel.requeued == [(7, True)]
+    assert closed == [True]
+
+    processed = []
+    def success(raw):
+        assert channel.acked == []
+        processed.append(raw)
+    assert broker.consume_one("order.events", success)
+    assert processed and channel.acked == [7]
diff --git a/tests/test_order.py b/tests/test_order.py
index ddad5f2..0ea1356 100644
--- a/tests/test_order.py
+++ b/tests/test_order.py
@@ -7,6 +7,7 @@ os.environ["JWT_SECRET"] = "order-unit-test-secret-with-32-plus-bytes!!"
 os.environ["RABBITMQ_URL"] = "memory://local"
 os.environ["PRODUCT_URL"] = "http://product:8000"
 os.environ["EXCHANGE_URL"] = "http://exchange:8000"
+os.environ["ENABLE_DEMO_CONTROLS"] = "true"
 
 from fastapi.testclient import TestClient
 import httpx
@@ -170,3 +171,11 @@ def test_order_creation_isolation_conversion_and_async_messaging():
         broker.available = True
         drain_queue_once()
         assert client.get(f"/orders/{outage_order_id}/notifications", headers=auth1).json()["status"] == "PROCESSED"
+
+
+def test_global_consumer_control_is_disabled_without_explicit_opt_in(monkeypatch):
+    monkeypatch.delenv("ENABLE_DEMO_CONTROLS", raising=False)
+    with TestClient(app) as client:
+        response = client.post("/orders/events/consumer", json={"enabled": False},
+                               headers={"Authorization": "Bearer " + make_token()})
+        assert response.status_code == 404
```

## 4. Exchange

Nenhuma mudança de código de integração foi aplicada em Exchange. Preservar `/exchanges/{from}/{to}`, validação JWT, `sell`, `buy`, `date`, `id-account` e consulta externa real. A conversão de Order usa `sell` e arredondamento por item em `ROUND_HALF_UP`, sem alterar USD persistido. O alias `/exchange/...` não substitui o caminho canônico do Gateway.

Preparar o ajuste de Jenkinsfile abaixo também em Exchange. Reexecutar seus testes. Não trocar consulta externa por valores simulados no aceite final.

## 5. Ajuste dos três Jenkinsfiles da Pessoa B

Aplica-se a Product, Order e Exchange. A linha atual de `stage('Test')` termina com quatro aspas simples contíguas após `pytest -q`, misturando o fechamento da string do shell com o delimitador Groovy. Separar esses fechamentos para eliminar a ambiguidade. Esse ponto foi identificado na leitura do arquivo; a compilação real no Jenkins ainda será validada depois.

Substituir **somente o estágio de teste** por este bloco nos três arquivos:

```groovy
stage('Test') {
  steps {
    sh '''
      docker run --rm \
        -v "$PWD:/src:ro" \
        -e PYTHONPATH=/src \
        -w /tmp \
        python:3.12-slim \
        sh -ec '
          pip install -r /src/requirements.txt
          python -m pytest /src/tests -q -p no:cacheprovider
        '
    '''
  }
}
```

O checkout é montado somente para leitura; SQLite temporário dos testes fica em `/tmp`, evitando lixo de testes no workspace. Esse estágio usa as dependências de cada serviço; os testes unitários usam os doubles de memória já previstos. O aceite integrado da raiz usa Redis/RabbitMQ reais.

Não remover a sequência Checkout → Test → Build → Publish → Deploy. Preservar:

- agente Linux `docker-kubectl` com Docker funcional e kubectl;
- `DOCKERHUB_NAMESPACE` válido e imagem `store-<serviço>:<SHA completo do commit>`;
- `DEPLOY=false` na primeira validação;
- credencial Jenkins `dockerhub` para publicação;
- credencial `store-kubeconfig` para deploy;
- credencial de leitura dos repositórios privados configurada no SCM de cada job;
- validação server-side do manifesto e espera pelo rollout antes de alegar sucesso;
- falha de teste interrompendo os estágios seguintes;
- credenciais reais fora de Git/ConfigMap, sem imprimir senhas/tokens.

O job de integração do `store-root` já usa `github-read`, Git tool `Default`, porta 18080 e os seis serviços. Ele ainda não foi executado em um Jenkins real. Não contar presença do Jenkinsfile como evidência de pipeline funcionando.

## 6. Contrato de configuração compartilhado — já preparado em A/root

Não precisa reimplementar estas mudanças no `store-root`; usar a versão publicada e combinar alterações de contratos com A.

| Serviço | Variável da aplicação | Chave de `store-secrets` no Kubernetes |
|---|---|---|
| Product | `JWT_SECRET` | `JWT_SECRET` |
| Product | `DATABASE_URL` | `PRODUCT_DATABASE_URL` |
| Product | `REDIS_URL` | `REDIS_URL` |
| Order | `JWT_SECRET` | `JWT_SECRET` |
| Order | `DATABASE_URL` | `ORDER_DATABASE_URL` |
| Order | `RABBITMQ_URL` | `RABBITMQ_URL` |
| Exchange | `JWT_SECRET` | `JWT_SECRET` |

- Namespace: `store`; Services internos: `product:8000`, `order:8000`, `exchange:8000`, `redis:6379`, `rabbitmq:5672`. Só Gateway publica API externa.
- JWT HS256, issuer `store-auth`, audience `store-api`, sub igual ao UUID da conta, `iat` e `exp`; manter validação nos próprios serviços.
- A raiz possui `compose.business.yaml`: PostgreSQL separado por serviço, senhas aleatórias, Redis autenticado e RabbitMQ com usuário `store` e senha aleatória.
- `scripts/setup-local.py` acrescenta as chaves ausentes sem substituir segredos reais já existentes. Não compartilhar o `.env`.
- A raiz já aplica DNS de timeout reduzido em Product e Order no Compose.
- RabbitMQ tem hostname estável e correção de permissão do cookie no volume. Não apagar volumes como solução para falha de inicialização.
- `scripts/k8s-secrets.py --business` prepara as referências novas. Para local, combinar com `--local-database`; para AWS, fornecer URLs reais e bancos/usuários próprios. Não apontar Product e Order ao banco de Account.
- `scripts/deploy-local.ps1 -Business` sobe os seis serviços e dependências. Antes, construir/carregar as imagens atualizadas no Kind.
- `scripts/render-deploy.py` aceita as três imagens de B junto das de A, todas com SHA completo.
- O Gateway encaminha `X-Cache-Control` somente para Product, além dos headers de autenticação calculados/validados. A mudança de A permanece no repositório de A.
- Os testes `tests/business_integration.py` e `tests/business_resilience.py` da raiz já estão disponíveis. O primeiro exige o controle global desabilitado por padrão.

## 7. Ordem para fazer agora

1. Alinhar os branches locais ao rollback, preservando trabalho próprio antes de qualquer reset.
2. Implementar o patch de Product e o patch de Order; revisar cada trecho. Não modificar Exchange sem necessidade além da preparação do seu Jenkinsfile.
3. Ajustar o estágio `Test` dos três Jenkinsfiles.
4. Rodar os testes unitários; em Order, esperar três testes principais aprovados, incluindo regressões. Product e Exchange tinham um teste principal cada na versão analisada.
5. Conferir a identidade Git e criar commits novos da Pessoa B, depois publicar nos próprios repositórios.
6. Informar a A os três SHAs finais. A atualiza os ponteiros dos submódulos no `store-root`, sem criar commits nos repositórios de B.
7. Repetir o aceite integrado e as falhas controladas. Só então validar Jenkins.

Não voltar a publicar os commits retirados do histórico nem declarar os relatórios antigos como validação dos novos commits. Os testes passaram na versão corrigida anterior ao rollback; precisam ser reproduzidos na implementação que B publicar.

## 8. Testar antes do Jenkins

Dentro de cada repositório, usar ambiente virtual próprio e dependências do respectivo `requirements.txt`, ou executar em container. Os testes criam banco SQLite temporário e doubles de cache/broker; não rodar no mesmo processo Python misturando as três aplicações.

Exemplo Linux, a partir do diretório de cada serviço:

```bash
docker run --rm -v "$PWD:/src:ro" -e PYTHONPATH=/src -w /tmp \
  python:3.12-slim sh -ec 'pip install -r /src/requirements.txt; python -m pytest /src/tests -q -p no:cacheprovider'
```

Na raiz, depois que A atualizar os ponteiros para os commits publicados por B:

```powershell
git submodule update --init --recursive
python scripts/setup-local.py
docker compose -f compose.yaml -f compose.business.yaml up --build -d
python tests/smoke.py
python tests/business_integration.py
python tests/business_resilience.py
```

O teste de resiliência interrompe/reinicia apenas Redis/RabbitMQ do projeto Compose local. Executar sem tráfego de outras pessoas; não apontar a um ambiente compartilhado. Confere expiração de uma chave de fixture no Redis, fallback ao banco, pedido 201 com broker parado, outbox pendente e processamento após retomada.

No Kubernetes, após carregar as seis imagens novas:

```powershell
./scripts/deploy-local.ps1 -Context kind-microserv-store -Business
kubectl --context kind-microserv-store -n store port-forward service/gateway 8082:8000
```

Em outro terminal:

```powershell
$env:BASE_URL='http://127.0.0.1:8082'
python tests/business_integration.py
```

Esperado: 40 verificações no aceite, incluindo produtos, propriedade de pedidos, conversão real, USD inalterado, Redis, RabbitMQ, replay idempotente e controle global desabilitado. A quantidade pode aumentar se um polling precisar de novas tentativas. BRL varia com a cotação externa.

## 9. O que validaremos no Jenkins depois

- Compilação dos três Jenkinsfiles, checkout privado e execução dos testes em agente limpo.
- Teste deliberadamente falhando bloqueia build/publicação/deploy subsequentes.
- Build e publicação dos três serviços de B, incluindo Exchange, com tags SHA.
- Credenciais e namespace corretos; Secrets/bancos/broker/cache existentes antes do deploy.
- `DEPLOY=true` somente quando o cluster de destino estiver escolhido e configurado.
- Mudança de código chega ao cluster e fica acessível pelo Gateway; rollback para imagem anterior.
- Job integrado da raiz clona os sete submódulos, usa porta isolada e executa os dois aceites.
- Evidências de autoria, SHA → imagem → rollout e resultados, sem senhas nos logs.

## 10. Pendências identificadas que os patches não resolvem sozinhos

- Cache-aside não oferece consistência forte: leitura concorrente com exclusão ou invalidação perdida durante falha do Redis pode manter dado obsoleto até o TTL. O aceite verificou sequências normais e fallback de leitura, não todas as corridas possíveis. Registrar o limite; se for exigida consistência forte, discutir invalidação/versionamento adicional antes de prometer essa garantia.
- A regressão de ACK verifica a ordem e o requeue, e o teste real verifica parada/retomada do broker. Não é teste de kill exatamente durante commit, nem garantia de exatamente uma vez.
- Validar os budgets de DNS/timeouts novamente no EKS; as medidas foram locais.
- EKS, RDS real, TLS público, custos completos e execução remota Jenkins ainda precisam de validação no ambiente de destino.
- Manter MkDocs Material e GitHub Pages públicos de B atualizados com contratos, cache, fila, limites, testes, autoria, uso de IA e links. Vídeo de dupla e defesa não são substituídos por testes automatizados.
