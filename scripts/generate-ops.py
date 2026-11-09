"""Generate service-local manifests and Jenkinsfiles; review changes before committing."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
for service in ("account", "auth", "gateway"):
    memory = "512Mi" if service == "auth" else "128Mi"
    cpu = "250m" if service == "auth" else "100m"
    limit = "768Mi" if service == "auth" else "256Mi"
    metrics = "/actuator/prometheus" if service == "auth" else "/metrics"
    env = ""
    if service == "account":
        env += '''        - name: DATABASE_URL
          valueFrom:
            secretKeyRef: {name: store-secrets, key: DATABASE_URL}
'''
    if service in ("account", "auth"):
        env += '''        - name: INTERNAL_AUTH_KEY
          valueFrom:
            secretKeyRef: {name: store-secrets, key: INTERNAL_AUTH_KEY}
'''
    if service in ("auth", "gateway"):
        for target in (("account",) if service == "auth" else ("account", "auth", "product", "order", "exchange")):
            env += f'''        - name: {target.upper()}_URL
          value: http://{target}:8000
'''
    manifest = f'''apiVersion: v1
kind: ConfigMap
metadata:
  name: {service}-config
  namespace: store
data:
  SERVICE_NAME: {service}
  TOKEN_TTL_SECONDS: "1800"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {service}
  namespace: store
spec:
  replicas: 2
  revisionHistoryLimit: 3
  strategy:
    rollingUpdate: {{maxUnavailable: 0, maxSurge: 1}}
  selector:
    matchLabels: {{app: {service}}}
  template:
    metadata:
      labels: {{app: {service}}}
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8000"
        prometheus.io/path: {metrics}
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        fsGroup: 10001
      terminationGracePeriodSeconds: 30
      containers:
      - name: {service}
        image: microserv-store/{service}:local
        imagePullPolicy: IfNotPresent
        ports: [{{containerPort: 8000, name: http}}]
        envFrom: [{{configMapRef: {{name: {service}-config}}}}]
        env:
        - name: JWT_SECRET
          valueFrom:
            secretKeyRef: {{name: store-secrets, key: JWT_SECRET}}
{env}        resources:
          requests: {{cpu: {cpu}, memory: {memory}}}
          limits: {{cpu: "1", memory: {limit}}}
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities: {{drop: [ALL]}}
        volumeMounts: [{{name: tmp, mountPath: /tmp}}]
        startupProbe:
          httpGet: {{path: /health-check, port: http}}
          failureThreshold: 60
          periodSeconds: 2
        readinessProbe:
          httpGet: {{path: /ready, port: http}}
          periodSeconds: 5
        livenessProbe:
          httpGet: {{path: /health-check, port: http}}
          periodSeconds: 10
      volumes: [{{name: tmp, emptyDir: {{}}}}]
---
apiVersion: v1
kind: Service
metadata:
  name: {service}
  namespace: store
spec:
  type: ClusterIP
  selector: {{app: {service}}}
  ports: [{{port: 8000, targetPort: http, name: http}}]
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {service}
  namespace: store
spec:
  scaleTargetRef: {{apiVersion: apps/v1, kind: Deployment, name: {service}}}
  minReplicas: 2
  maxReplicas: 5
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 60
  metrics:
  - type: Resource
    resource:
      name: cpu
      target: {{type: Utilization, averageUtilization: 60}}
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {service}
  namespace: store
spec:
  minAvailable: 1
  selector:
    matchLabels: {{app: {service}}}
'''
    base = root / "api" / service
    (base / "k8s").mkdir(exist_ok=True)
    (base / "k8s/k8s.yaml").write_text(manifest)
    # Real secrets are provisioned once, independently from service pipelines.
    test = {"account": "docker run --rm -v \"$PWD:/src\" -w /src python:3.12-slim sh -c 'pip install -r requirements.txt && python -m pytest -q'",
            "auth": "docker run --rm -v \"$PWD:/src\" -w /src maven:3.9-eclipse-temurin-21 mvn -B verify",
            "gateway": "docker run --rm -v \"$PWD:/src\" -w /src golang:1.24-bookworm go test ./..."}[service]
    jenkins = '''pipeline {
  agent { label 'docker-kubectl' }
  options { timestamps(); disableConcurrentBuilds() }
  parameters {
    string(name: 'DOCKERHUB_NAMESPACE', defaultValue: '', description: 'Required Docker Hub namespace')
    booleanParam(name: 'DEPLOY', defaultValue: false, description: 'Deploy using the dedicated kubeconfig credential')
  }
  stages {
    stage('Checkout') { steps { checkout scm } }
    stage('Test') { steps { sh SCRIPT_TEST } }
    stage('Build') {
      steps {
        script {
          if (!params.DOCKERHUB_NAMESPACE.matches('[a-z0-9][a-z0-9_-]*')) { error('Invalid registry namespace') }
          env.IMAGE_TAG = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
          env.IMAGE = "${params.DOCKERHUB_NAMESPACE}/store-SERVICE:${env.IMAGE_TAG}"
        }
        sh 'docker build -t "$IMAGE" .'
      }
    }
    stage('Publish') {
      steps {
        withCredentials([usernamePassword(credentialsId: 'dockerhub', usernameVariable: 'REGISTRY_USER', passwordVariable: 'REGISTRY_PASSWORD')]) {
          sh \u0027\u0027\u0027
            set +x
            export DOCKER_CONFIG=$(mktemp -d)
            trap 'rm -rf "$DOCKER_CONFIG"' EXIT
            printf '%s' "$REGISTRY_PASSWORD" | docker login -u "$REGISTRY_USER" --password-stdin
            docker push "$IMAGE"
          \u0027\u0027\u0027
        }
      }
    }
    stage('Deploy') {
      when { expression { params.DEPLOY } }
      steps {
        withCredentials([file(credentialsId: 'store-kubeconfig', variable: 'KUBECONFIG')]) {
          sh \u0027\u0027\u0027
            set -eu
            sed "s|image: microserv-store/SERVICE:local|image: $IMAGE|" k8s/k8s.yaml > deployment.rendered.yaml
            kubectl apply --dry-run=server -f deployment.rendered.yaml
            kubectl apply -f deployment.rendered.yaml
            kubectl rollout status deployment/SERVICE -n store --timeout=180s
          \u0027\u0027\u0027
        }
      }
    }
  }
  post { always { archiveArtifacts artifacts: 'deployment.rendered.yaml', allowEmptyArchive: true } }
}
'''.replace("SERVICE", service).replace("SCRIPT_TEST", "'''" + test + "'''")
    (base / "Jenkinsfile").write_text(jenkins)
print("Generated Kubernetes and Jenkins configuration")
