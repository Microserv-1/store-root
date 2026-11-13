# Fechamento da entrega — Pessoa B

Registro de 13/11/2026. Não substitui o handoff anterior. Este arquivo reúne
ajustes de documentação e revisão que B deve publicar com sua autoria.

## Versões executadas no EKS

| Serviço | Commit |
|---|---|
| Product | `c40bec1c96f786d11c89c021f7fb891af2bd048c` |
| Order | `a97fe5583e8e0e3615aab062a570bd2263b57089` |
| Exchange | `ea580c5b6e8c6eb6f552ac56390764a2f215c76f` |

Release Jenkins da raiz `6617d8774baabe5943b9cbf4ec2e9a257edf3a97`:
checkout GitHub recursivo, dez verificações de preparação, preflight AWS,
dry-run, aplicação e rollout dos seis serviços concluídos com SUCCESS.
Account/Auth/Gateway usam respectivamente `7b61a3d`, `d803717`, `a394417`.
As tags completas e digests estão em `infra/aws/images.lock.json` na raiz.

## Atualizações a fazer em store-docs-b

- Atualizar `status.md` e `deploy.md`: EKS/RDS/Jenkins remoto executados em
  13/11; manter resultados anteriores identificados como históricos.
- Vincular as evidências de nuvem de A em `evidence/2026-11-13-eks/` e a página
  de fechamento. O aceite real passou em 40 verificações, com Redis, RabbitMQ
  e câmbio `open-er-api`; USD 26,44 convertido para BRL 149,08 naquela rodada.
- Corrigir `operations.md`: dois workers **t3.large**, Jenkins **t3.large**,
  RDS **db.t4g.small** Single-AZ, 20 GiB, e **nenhum ALB** na implantação atual.
  O acesso é port-forward; Redis e RabbitMQ permanecem no cluster. Não indicar
  ElastiCache/Amazon MQ como serviços efetivamente provisionados.
- Distinguir benchmark antigo de cache/fila e versão atual de B. O teste
  funcional EKS confirmou HIT/BYPASS/invalidação e replay sem duplicar a
  notificação; não atribuir a essa execução ganhos de desempenho históricos.
- Conferir o enquadramento dos dois gargalos individuais: Redis e mensageria;
  explicar problema, implementação, limites e evidências. Não alegar garantia
  de exatamente uma vez em todas as janelas de falha.
- Vincular apresentação, vídeo final de 1–2 minutos e gravação técnica EKS
  quando efetivamente produzidos. Não marcar vídeos como entregues antes disso.
- Revalidar a revisão cruzada na versão final; registrar data, pessoa, commit,
  cenário e resultado. Participar do ensaio e conseguir explicar toda a solução.
- Conferir acesso do professor aos repositórios privados e enviar o próprio
  site no Blackboard, guardando a confirmação. Confirmar horário de 16/11.

## Limite de custo compartilhado

Yuri fixou teto adicional de **US$ 20**, incluindo manutenção dos recursos
existentes a partir desta decisão. Não iniciar carga, novos builds na AWS,
recursos, nós ou mudanças com potencial de custo adicional sem alinhar com ele.
O custo fixo estimado atual é cerca de US$ 0,44/h, mais variáveis; 72 horas
contínuas excedem o teto. Não desligar nem excluir recursos sem combinar a
janela de avaliação e a preservação dos dados.

## Confirmações externas ainda necessárias

Rubrica aplicável e seus pesos; contratos originais de Account/Auth/Gateway;
aceitação de Kind para QA local caso Minikube seja nominalmente obrigatório;
se a avaliação exige uma URL pública da API (o site de documentação é público,
mas a API está privada). São verificações com o professor/material, não motivos
para inventar requisitos ou refazer serviços sem necessidade.
