# Ajustes necessários na documentação de B

Não foi identificada necessidade de mudar código em Product, Order ou
Exchange no aceite EKS: os seis serviços passaram em 40 verificações reais.
Nenhum arquivo ou commit foi criado por A nos seus três microsserviços.

Versões testadas: Product `c40bec1`, Order `a97fe55`, Exchange `ea580c5`.
Release da raiz: `6617d8774baabe5943b9cbf4ec2e9a257edf3a97`.

## Atualizar no seu store-docs-b

1. **status.md / deploy.md:** EKS, RDS e Jenkins remoto foram executados com
   sucesso em 13/11/2026. Marcar os registros antigos como históricos.
2. **operations.md:** a implantação real usa dois workers `t3.large`,
   Jenkins `t3.large`, RDS `db.t4g.small` Single-AZ com 20 GiB, Redis/RabbitMQ
   no cluster e acesso por port-forward, sem ALB. Corrigir as classes antigas.
3. **Evidências:** vincular os registros abaixo. O aceite atual comprovou
   cache HIT/BYPASS/invalidação e replay idempotente; não transferir ganhos de
   benchmarks antigos para esta rodada ou para commits diferentes.
4. **Entrega individual:** depois de produzidos, vincular apresentação e
   vídeos, registrar revisão cruzada e enviar seu próprio site no Blackboard.
   HPA EKS e vídeo final ainda não estão concluídos.

Referências prontas para compartilhar por link:

- [Deploy e pendências](https://microserv-1.github.io/store-docs-a/closure/).
- [Aceite real no EKS](https://microserv-1.github.io/store-docs-a/evidence/2026-11-13-eks/business-integration.json).
- [Custos da infraestrutura real](https://microserv-1.github.io/store-docs-a/operations/).

Publique apenas seus próprios commits. Não é necessário refazer os serviços.
O teto adicional compartilhado é US$ 20: não iniciar carga/builds/recursos na
AWS sem alinhar com Yuri; a configuração ligada custa cerca de US$ 0,44/h
mais variáveis. Não parar ou excluir recursos sem combinar a avaliação.
