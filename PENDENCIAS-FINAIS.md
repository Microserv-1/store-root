# Decisões finais — Yuri e Gustavo

Estado em 14/11/2026. A aplicação e a bateria técnica estão validadas no EKS.
Nenhuma das decisões abaixo foi presumida como respondida.

## 1. AWS: escolher uma opção

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

Informar em uma resposta: nome acadêmico completo de Yuri, grupo e edição
correta do curso. O site usa o nome conhecido, com confirmação pendente.
Não inventar identificação nem alterar autoria de commits antigos.

## 3. Vídeo e apresentação

O agente produziu um vídeo curto de apresentação, com voz sintética
identificada, arquitetura e resultados reais. Não registra a voz, a imagem
ou a participação oral de um aluno. Confirmar na rubrica se essa forma de
narração é aceita; se exigir participação dos dois, substituir/complementar
a narração com gravações reais da dupla, usando o material preparado.

Os vídeos técnicos de cluster/HPA ficam separados, para não ultrapassar o
limite de 1–2 minutos do vídeo curto. O arquivo de slides nativo/editável
continua pendente por falha do serviço de apresentações; o roteiro e os
quadros usados no vídeo estão disponíveis. Não apresentar um documento
vazio como slides prontos.

## 4. AWS Pricing Calculator

A estimativa rastreável já existe: US$ 209,54 por 730h e US$ 20,67 por 72h
futuras, antes de variáveis. Falta o link/exportação emitido pelo Calculator.
O controle do navegador está indisponível para o agente. A dupla pode preencher
os [parâmetros preparados](https://microserv-1.github.io/store-docs-a/calculator-inputs/)
e fornecer o link/exportação, ou aguardar o controle funcionar. Não é preciso
criar recursos AWS para usar o Calculator.

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
AWS: manter / pausar / encerrar (com decisão de retenção dos dados)
Nome completo de Yuri:
Grupo e edição:
Narração sintética: aceita / precisa de voz dos alunos / vou confirmar
Calculator: vou preencher e enviar o link / aguardar o navegador
Rubrica, URL pública e Kind: confirmação ou pendências
```

O agente cuida da publicação e dos ajustes autorizados. Nenhuma revisão,
participação humana, confirmação acadêmica ou submissão é registrada antes
de acontecer.
