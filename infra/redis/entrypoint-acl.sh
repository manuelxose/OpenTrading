#!/bin/sh
# Redis production entrypoint (ADR-0025): ACL-first startup.
#
# Writes an ACL file from the container environment and starts redis-server with
# `protected-mode`. Apps authenticate as `opentrading` (no @admin/@dangerous/
# @scripting); the exporter has a read-only user. The `default` user is disabled.
set -e

: "${REDIS_PASSWORD:?REDIS_PASSWORD is required}"
: "${REDIS_EXPORTER_PASSWORD:?REDIS_EXPORTER_PASSWORD is required}"

umask 077
cat > /tmp/redis-acl.conf <<EOF
user default off
user opentrading on >"${REDIS_PASSWORD}" ~* +@all -@admin -@dangerous -@scripting
user redis-exporter on >"${REDIS_EXPORTER_PASSWORD}" ~* +INFO +PING +SLOWLOG +CLIENT +COMMAND +CLUSTER +CONFIG|GET
EOF

exec redis-server --appendonly yes --aclfile /tmp/redis-acl.conf --protected-mode yes "$@"
