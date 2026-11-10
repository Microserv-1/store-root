import json
from pathlib import Path
queries = [
    ("Services up", "up", "short"),
    ("Gateway throughput", "sum(rate(gateway_request_duration_seconds_count[1m]))", "reqps"),
    ("Gateway p95", "histogram_quantile(0.95, sum by (le) (rate(gateway_request_duration_seconds_bucket[1m])))", "s"),
    ("Account errors / s", 'sum(rate(http_requests_total{job="account",status=~"5.."}[1m]))', "reqps"),
    ("Account CPU cores", 'rate(process_cpu_seconds_total{job="account"}[1m])', "short"),
    ("Account resident memory", 'process_resident_memory_bytes{job="account"}', "bytes"),
    ("Auth JVM memory", 'sum(jvm_memory_used_bytes{job="auth"})', "bytes"),
    ("Auth HTTP p95", 'histogram_quantile(0.95, sum by(le) (rate(http_server_requests_seconds_bucket{job="auth"}[1m])))', "s"),
    ("Product Redis Cache Hits vs Misses / s", "sum by (operation) (rate(product_cache_hits_total[1m])) or sum by (operation) (rate(product_cache_misses_total[1m]))", "reqps"),
    ("Order Events Published vs Consumed", "sum(order_events_published_total) or sum(order_events_consumed_total)", "short"),
    ("Exchange External Provider Calls", "sum by (provider, status) (exchange_external_requests_total)", "short"),
    ("Business Services CPU cores", 'sum by (job) (rate(process_cpu_seconds_total{job=~"product|order|exchange"}[1m]))', "short"),
]
panels = []
for i,(title,query,unit) in enumerate(queries):
    panels.append({"id":i+1,"title":title,"type":"timeseries","datasource":{"type":"prometheus","uid":"prometheus"},
      "gridPos":{"x":(i%2)*12,"y":(i//2)*8,"w":12,"h":8},
      "targets":[{"expr":query,"refId":"A"}],"fieldConfig":{"defaults":{"unit":unit}}})
dashboard={"title":"Store — Plataforma Integrada (A + B)", "uid":"store-a", "schemaVersion":41,"version":2,
           "refresh":"5s", "time":{"from":"now-15m","to":"now"},"panels":panels}
path=Path("infra/monitoring/grafana/dashboards/store.json")
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(dashboard,indent=2))
