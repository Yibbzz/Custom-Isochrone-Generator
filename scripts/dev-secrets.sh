#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Creates the dev Kubernetes secrets that the isochrone-app Helm chart
# references (postgres-secret, django-secret).
#
# - No secret VALUES live in this file or in git. They are generated at run
#   time and written straight into the cluster.
# - Safe to re-run: existing secrets are left untouched, so it will NOT rotate
#   the Postgres password out from under an already-initialised database.
# - Guards against running on the wrong cluster.
#
# Usage:
#   ./scripts/dev-secrets.sh
#   NAMESPACE=default EXPECTED_CONTEXT=k3d-k3d-cluster-1 ./scripts/dev-secrets.sh
# ---------------------------------------------------------------------------

NAMESPACE="${NAMESPACE:-default}"
EXPECTED_CONTEXT="${EXPECTED_CONTEXT:-k3d-k3d-cluster-1}"

current_context="$(kubectl config current-context)"
if [[ "$current_context" != "$EXPECTED_CONTEXT" ]]; then
  echo "Refusing to run: kubectl context is '$current_context', expected '$EXPECTED_CONTEXT'." >&2
  echo "If that is intentional, re-run with:" >&2
  echo "  EXPECTED_CONTEXT='$current_context' $0" >&2
  exit 1
fi

secret_exists() {
  kubectl get secret "$1" -n "$NAMESPACE" >/dev/null 2>&1
}

if secret_exists postgres-secret; then
  echo "postgres-secret already exists in '$NAMESPACE' - leaving it unchanged."
else
  PG_PASS="$(openssl rand -base64 24)"
  kubectl create secret generic postgres-secret \
    --from-literal=POSTGRES_USER=postgres \
    --from-literal=POSTGRES_PASSWORD="$PG_PASS" \
    -n "$NAMESPACE"
  echo "Created postgres-secret."
fi

if secret_exists django-secret; then
  echo "django-secret already exists in '$NAMESPACE' - leaving it unchanged."
else
  DJ_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
  kubectl create secret generic django-secret \
    --from-literal=DJANGO_SECRET_KEY="$DJ_KEY" \
    -n "$NAMESPACE"
  echo "Created django-secret."
fi

echo
echo "Done. Secrets in namespace '$NAMESPACE':"
kubectl get secret postgres-secret django-secret -n "$NAMESPACE"