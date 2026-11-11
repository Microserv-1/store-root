#!/bin/sh
set -eu
# Repair only the broker's cookie ownership before the official entrypoint drops privileges.
if [ -f /var/lib/rabbitmq/.erlang.cookie ]; then
  chown rabbitmq:rabbitmq /var/lib/rabbitmq/.erlang.cookie
  chmod 400 /var/lib/rabbitmq/.erlang.cookie
fi
exec docker-entrypoint.sh rabbitmq-server
