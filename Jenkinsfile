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
        sh 'python3 scripts/setup-local.py'
        sh 'docker compose -p store-integration build'
      }
    }
    stage('Integration') {
      steps {
        sh 'docker compose -p store-integration up -d'
        sh 'python3 tests/smoke.py'
      }
    }
  }
  post {
    always { sh 'docker compose -p store-integration down' }
  }
}
