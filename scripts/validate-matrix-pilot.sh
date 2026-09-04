#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose_file="$repo_root/deploy/matrix/compose.yaml"

python3 "$repo_root/deploy/matrix/validate.py"
docker compose --file "$compose_file" config --quiet

if [ "${1:-}" != "--smoke" ]; then
    echo "Matrix pilot static checks passed. Add --smoke to start local containers."
    exit 0
fi

project_name="ratichat-matrix-pilot-smoke"

cleanup() {
    docker compose --project-name "$project_name" --file "$compose_file" down --volumes --remove-orphans
}

trap cleanup EXIT INT TERM

docker compose --project-name "$project_name" --file "$compose_file" up --detach --build

wait_for_url() {
    label=$1
    url=$2
    attempts=60

    while [ "$attempts" -gt 0 ]; do
        if curl --fail --silent --show-error "$url" >/dev/null 2>&1; then
            echo "$label is ready."
            return 0
        fi
        attempts=$((attempts - 1))
        sleep 1
    done

    echo "$label did not become ready at $url" >&2
    return 1
}

wait_for_url "Continuwuity" "http://127.0.0.1:8008/_matrix/client/versions"
wait_for_url "Pocket ID" "http://127.0.0.1:1411/healthz"
wait_for_url "Element Web" "http://127.0.0.1:8080/config.json"

echo "Matrix pilot local smoke checks passed."
