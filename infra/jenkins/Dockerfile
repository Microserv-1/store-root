FROM docker:29-cli AS dockercli
FROM jenkins/jenkins:lts-jdk21
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates curl git && rm -rf /var/lib/apt/lists/*
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins /usr/local/libexec/docker/cli-plugins
RUN curl -fsSL https://dl.k8s.io/release/v1.32.2/bin/linux/amd64/kubectl -o /usr/local/bin/kubectl \
 && curl -fsSL https://dl.k8s.io/release/v1.32.2/bin/linux/amd64/kubectl.sha256 -o /tmp/kubectl.sha256 \
 && echo "$(cat /tmp/kubectl.sha256)  /usr/local/bin/kubectl" | sha256sum --check \
 && chmod +x /usr/local/bin/kubectl
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
COPY init.groovy /usr/share/jenkins/ref/init.groovy.d/store.groovy
USER jenkins
