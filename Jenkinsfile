// Team integration job. Service repositories each own their build/publish/deploy job.
pipeline {
  agent { label 'docker-kubectl' }
  options { timestamps(); disableConcurrentBuilds() }
  environment {
    GATEWAY_PORT = '18080'
    BASE_URL = 'http://127.0.0.1:18080'
  }
  stages {
    stage('Checkout recursively') {
      steps {
        checkout scm
        withCredentials([gitUsernamePassword(credentialsId: 'github-read', gitToolName: 'Default')]) {
          sh 'git submodule update --init --recursive'
        }
      }
    }
    stage('Prepare isolated integration environment') {
      steps {
        sh 'mkdir -p artifacts && rm -f artifacts/business-integration.json artifacts/integration-services.log'
        sh 'python3 scripts/setup-local.py'
        sh 'docker compose -p store-integration -f compose.yaml -f compose.business.yaml build'
      }
    }
    stage('Integration') {
      steps {
        sh 'docker compose -p store-integration -f compose.yaml -f compose.business.yaml up -d'
        script {
          def endpoint = env.BASE_URL
          if (env.STORE_JENKINS_CONTAINER_NETWORK == 'true') {
            sh 'docker network connect store-integration_backend "$HOSTNAME"'
            endpoint = 'http://store-integration-gateway-1:8000'
          }
          withEnv(["BASE_URL=${endpoint}"]) {
            sh 'python3 tests/smoke.py'
            sh 'python3 tests/business_integration.py'
          }
        }
      }
    }
  }
  post {
    always {
      sh(returnStatus: true, script: 'mkdir -p artifacts; docker compose -p store-integration -f compose.yaml -f compose.business.yaml logs --no-color --tail=100 > artifacts/integration-services.log 2>&1')
      archiveArtifacts artifacts: 'artifacts/business-integration.json,artifacts/integration-services.log', allowEmptyArchive: true
      script {
        if (env.STORE_JENKINS_CONTAINER_NETWORK == 'true') {
          sh(returnStatus: true, script: 'docker network disconnect store-integration_backend "$HOSTNAME"')
        }
      }
      sh 'docker compose -p store-integration -f compose.yaml -f compose.business.yaml down -v'
    }
  }
}
