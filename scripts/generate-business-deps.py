"""Generate local Kubernetes dependencies without embedding credentials."""
import json
from pathlib import Path

items=[]
def metadata(name):return {"name":name,"namespace":"store"}
def secret_env(name,key):return {"name":name,"valueFrom":{"secretKeyRef":{"name":"store-secrets","key":key}}}
def service(name,port):
    items.append({"apiVersion":"v1","kind":"Service","metadata":metadata(name),
       "spec":{"selector":{"app":name},"ports":[{"port":port,"targetPort":port}]}})
def pvc(name):
    items.append({"apiVersion":"v1","kind":"PersistentVolumeClaim","metadata":metadata(name),
       "spec":{"accessModes":["ReadWriteOnce"],"resources":{"requests":{"storage":"1Gi"}}}})
def deployment(name,container,volumes=None,init=None):
    spec={"automountServiceAccountToken":False,"containers":[container]}
    if name == "rabbitmq":spec["hostname"]="rabbitmq"
    if volumes:spec["volumes"]=volumes
    if init:spec["initContainers"]=init
    items.append({"apiVersion":"apps/v1","kind":"Deployment","metadata":metadata(name),
       "spec":{"replicas":1,"strategy":{"type":"Recreate"},"selector":{"matchLabels":{"app":name}},
         "template":{"metadata":{"labels":{"app":name}},"spec":spec}}})
for name,user,database,key in [("product-db","product","products","PRODUCT_DB_PASSWORD"),("order-db","orders","orders","ORDER_DB_PASSWORD")]:
    pvc(name+"-data")
    deployment(name,{"name":name,"image":"postgres:16-alpine",
        "env":[{"name":"POSTGRES_USER","value":user},{"name":"POSTGRES_DB","value":database},secret_env("POSTGRES_PASSWORD",key)],
        "ports":[{"containerPort":5432}],"resources":{"requests":{"cpu":"100m","memory":"128Mi"},"limits":{"cpu":"1","memory":"512Mi"}},
        "volumeMounts":[{"name":"data","mountPath":"/var/lib/postgresql/data"}],
        "readinessProbe":{"exec":{"command":["pg_isready","-U",user,"-d",database]},"periodSeconds":5}},
        [{"name":"data","persistentVolumeClaim":{"claimName":name+"-data"}}])
    service(name,5432)
deployment("redis",{"name":"redis","image":"redis:7-alpine",
    "command":["sh","-c",'exec redis-server --requirepass "$REDIS_PASSWORD"'],"env":[secret_env("REDIS_PASSWORD","REDIS_PASSWORD")],
    "ports":[{"containerPort":6379}],"resources":{"requests":{"cpu":"50m","memory":"32Mi"},"limits":{"cpu":"500m","memory":"128Mi"}}})
service("redis",6379)
pvc("rabbit-data")
mount=[{"name":"data","mountPath":"/var/lib/rabbitmq"}]
deployment("rabbitmq",{"name":"rabbitmq","image":"rabbitmq:4-alpine",
    "env":[{"name":"RABBITMQ_DEFAULT_USER","value":"store"},secret_env("RABBITMQ_DEFAULT_PASS","RABBITMQ_PASSWORD"),
           {"name":"RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS","value":"+S 2:2"}],
    "ports":[{"containerPort":5672}],"volumeMounts":mount,
    "resources":{"requests":{"cpu":"100m","memory":"128Mi"},"limits":{"cpu":"1","memory":"512Mi"}},
    "startupProbe":{"tcpSocket":{"port":5672},"failureThreshold":60,"periodSeconds":3},
    "readinessProbe":{"tcpSocket":{"port":5672},"periodSeconds":5}},
    [{"name":"data","persistentVolumeClaim":{"claimName":"rabbit-data"}}],
    [{"name":"cookie-permissions","image":"rabbitmq:4-alpine","securityContext":{"runAsUser":0},"volumeMounts":mount,
      "command":["sh","-c","if [ -f /var/lib/rabbitmq/.erlang.cookie ]; then chown rabbitmq:rabbitmq /var/lib/rabbitmq/.erlang.cookie; chmod 400 /var/lib/rabbitmq/.erlang.cookie; fi"]}])
service("rabbitmq",5672)
Path("infra/k8s/business-dependencies.json").write_text(json.dumps({"apiVersion":"v1","kind":"List","items":items},indent=2))
print("Generated local Product/Order databases, Redis and RabbitMQ")
