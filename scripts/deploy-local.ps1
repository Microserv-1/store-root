param([Parameter(Mandatory=$true)][string]$Context)
$ErrorActionPreference = 'Stop'
function Invoke-Kubectl {
    & kubectl --context $Context @args
    if ($LASTEXITCODE -ne 0) { throw 'kubectl failed' }
}
Invoke-Kubectl apply -f infra/k8s/namespace.yaml
python scripts/k8s-secrets.py --context $Context --local-database
if ($LASTEXITCODE -ne 0) { throw 'Secret provisioning failed' }
Invoke-Kubectl apply -f infra/k8s/postgres-local.yaml
Invoke-Kubectl rollout status deployment/postgres -n store --timeout=180s
foreach ($Service in 'account','auth','gateway') {
    Invoke-Kubectl apply -f "api/$Service/k8s/k8s.yaml"
    Invoke-Kubectl rollout status "deployment/$Service" -n store --timeout=180s
}
python scripts/deploy-monitoring.py --context $Context
if ($LASTEXITCODE -ne 0) { throw 'Monitoring deployment failed' }
Write-Host 'Ready. Forward gateway: kubectl --context <context> -n store port-forward service/gateway 8080:8000'
