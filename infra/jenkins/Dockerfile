FROM docker:29-cli AS dockercli
FROM public.ecr.aws/aws-cli/aws-cli:2.39.7@sha256:73f81e380c7974c9f03ac7ccd520ef080f17f443e10582f024c828b970ac8b73 AS awscli
FROM jenkins/jenkins:lts-jdk21
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates curl git && rm -rf /var/lib/apt/lists/*
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins /usr/local/libexec/docker/cli-plugins
COPY --from=awscli /usr/local/aws-cli /usr/local/aws-cli
RUN ln -s /usr/local/aws-cli/v2/current/bin/aws /usr/local/bin/aws && aws --version
ARG KUBECTL_VERSION=v1.35.0
RUN curl -fsSL https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl -o /usr/local/bin/kubectl \
 && curl -fsSL https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl.sha256 -o /tmp/kubectl.sha256 \
 && echo "$(cat /tmp/kubectl.sha256)  /usr/local/bin/kubectl" | sha256sum --check \
 && chmod +x /usr/local/bin/kubectl
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
COPY init.groovy /usr/share/jenkins/ref/init.groovy.d/store.groovy
USER jenkins
