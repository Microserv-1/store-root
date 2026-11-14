# Decisões finais — Yuri Henrique e Gustavo Lina

Estado em 14/11/2026. A bateria técnica foi validada no EKS. Yuri confirmou
os nomes, pediu vídeo sem narração e autorizou a pausa da AWS, que foi
executada preservando RDS, volume RabbitMQ e disco Jenkins.

## 1. AWS: pausa confirmada

Workers zerados/terminados, RDS e EC2 Jenkins parados. O [registro de pausa e
retomada](https://microserv-1.github.io/store-docs-a/aws-pause/) contém evidências.
As outras opções abaixo exigem nova autorização; a pausa não encerra custos.

| Opção | Consequência | Estimativa fixa futura |
|---|---|---:|
| Manter ligada | Aplicação disponível pelo túnel autorizado para avaliação | US$ 0,287/h; US$ 6,89/dia |
| Pausar workers, RDS e Jenkins | Aplicação indisponível; dados preservados e retomada necessária | Cerca de US$ 0,161/h; US$ 3,86/dia, estimativa conservadora |
| Encerrar definitivamente | Excluir infraestrutura e decidir/apagar dados, volumes e snapshots exclusivos | Exige auditoria de itens retidos; não prometer custo zero antes dela |

Valores não incluem variáveis nem descontam o gasto já acumulado do teto
adicional de US$ 20. Pausar não interrompe EKS/NAT/armazenamento. RDS parado
tem limite de sete dias e pode iniciar automaticamente. Encerrar não apaga
os repositórios, sites ou vídeos publicados no GitHub. O procedimento de
[encerramento](https://microserv-1.github.io/store-docs-a/aws-shutdown/) está
preparado; não foi executado.

## 2. Identificação acadêmica

Nomes informados e atualizados: **Yuri Henrique e Gustavo Lina**. Grupo e
edição acadêmica ainda não foram informados. Não inventar identificação nem
alterar autoria de commits antigos.

## 3. Vídeo e apresentação

O agente ajustou o vídeo curto para **1min56s, sem narração/faixa de áudio**,
conforme pedido de Yuri, com os nomes e os resultados reais. Ele não registra
participação oral; a defesa individual continua sendo dos alunos.

Os vídeos técnicos de cluster/HPA ficam separados, para não ultrapassar o
limite de 1–2 minutos do vídeo curto. Slides são os sete quadros de apoio
(objetivo, arquitetura, fluxo, gargalos, resultados e conclusão) já presentes
no vídeo. A exigência de um arquivo separado PowerPoint/PDF não foi confirmada;
não apresentá-la como requisito acadêmico comprovado. O material e roteiro
de apoio à apresentação estão preparados.

## 4. AWS Pricing Calculator

A estimativa rastreável já existe: US$ 209,54 por 730h e US$ 20,67 por 72h
futuras, antes de variáveis. Falta o link/exportação emitido pelo Calculator.
Yuri pediu o passo a passo para preencher manualmente; ele está nos
[parâmetros preparados](https://microserv-1.github.io/store-docs-a/calculator-inputs/).
Fornecer o link/exportação depois de preencher. Não é preciso criar recursos
AWS para usar o Calculator, nem retomar a aplicação pausada.

## 5. Documentação de Gustavo

Gustavo deve atualizar seu próprio `store-docs-b` com a implantação real,
máquinas menores e evidências da rodada final. As instruções resumidas estão
em [FECHAMENTO-PESSOA-B.md](FECHAMENTO-PESSOA-B.md). Não é necessária mudança
de código em Product, Order ou Exchange conforme os testes atuais. A não
publica commits nos repositórios de B.

## 6. Conferências acadêmicas e humanas

- Confirmar pesos da rubrica, contratos originais e horário do Blackboard.
- Confirmar se Kind é aceito no item local e se a API precisa de URL pública
  independente; o acesso atual é privado por port-forward, sem ALB.
- Cada pessoa executar/revisar um cenário do colega e registrar pessoa,
  data, commits e resultado real. Ensaio de defesa com os pontos preparados.
- Conferir o acesso do avaliador aos repositórios privados e links públicos.
- Cada integrante enviar seu próprio site no Blackboard e guardar recibo.

## Resposta única sugerida

```text
Grupo e edição:
Calculator: link/exportação após preencher
Rubrica, URL pública e Kind: confirmação ou pendências
```

O agente cuida da publicação e dos ajustes autorizados. Nenhuma revisão,
participação humana, confirmação acadêmica ou submissão é registrada antes
de acontecer.
