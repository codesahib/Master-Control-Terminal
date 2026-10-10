#!/usr/bin/env bash
# Back up the app database (public schema, pg_dump custom format) to a folder outside the repo.
#
# Source URL, first match wins: BACKUP_DATABASE_URL, then DATABASE_POOLER_URL, then DATABASE_URL
# (from the environment or the repo .env). Output: ${BACKUP_DIR:-$HOME/Backups/master-control-terminal}/<UTC>/public.dump
# Keeps the newest 14 automatic backups (folders named YYYYMMDDTHHMMSSZ); other folders are never touched.
#
# Nightly at 03:00 via cron (Docker must be on PATH):
#   0 3 * * * PATH=/usr/local/bin:/usr/bin:/bin /path/to/Master-Control-Terminal/scripts/backup.sh >> "$HOME/Backups/master-control-terminal/backup.log" 2>&1
# Restore: pg_restore --no-owner --no-acl -d <target-url> <folder>/public.dump
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
base_dir="${BACKUP_DIR:-$HOME/Backups/master-control-terminal}"
keep=14

env_value() {
  # Environment first, then the repo .env (value after the first "=", quotes stripped).
  local key="$1"
  if [ -n "${!key:-}" ]; then
    printf '%s' "${!key}"
  elif [ -f "$repo_dir/.env" ]; then
    grep -E "^${key}=" "$repo_dir/.env" | tail -n 1 | cut -d= -f2- | sed -e "s/^[\"']//" -e "s/[\"']$//"
  fi
}

url="${BACKUP_DATABASE_URL:-}"
[ -n "$url" ] || url="$(env_value DATABASE_POOLER_URL)"
[ -n "$url" ] || url="$(env_value DATABASE_URL)"
if [ -z "$url" ]; then
  echo "backup: no database URL (set BACKUP_DATABASE_URL, DATABASE_POOLER_URL or DATABASE_URL)" >&2
  exit 1
fi
# pg_dump wants a plain libpq URL; the dump runs inside Docker, so host-local DBs go through host.docker.internal.
url="${url/postgresql+psycopg:\/\//postgresql://}"
url="$(printf '%s' "$url" | sed -E 's#@(localhost|127\.0\.0\.1)([:/])#@host.docker.internal\2#')"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out_dir="$base_dir/$stamp"
umask 077
mkdir -p "$out_dir"
chmod 700 "$base_dir" "$out_dir"

# PGURL is passed by name so the URL never appears in the process list.
PGURL="$url" docker run --rm -e PGURL --user "$(id -u):$(id -g)" -v "$out_dir":/out postgres:17 \
  sh -c 'pg_dump "$PGURL" -n public --no-owner --no-acl -Fc -f /out/public.dump && pg_restore --list /out/public.dump > /out/contents.txt'
chmod 600 "$out_dir"/*

entries="$(grep -cv '^;' "$out_dir/contents.txt" || true)"
if [ "${entries:-0}" -eq 0 ]; then
  echo "backup: dump at $out_dir looks empty" >&2
  exit 1
fi
echo "backup: $out_dir/public.dump ($entries entries)"

# Retention: only folders this script creates.
ls -1 "$base_dir" | grep -E '^[0-9]{8}T[0-9]{6}Z$' | sort -r | tail -n +$((keep + 1)) | while read -r old; do
  rm -rf "${base_dir:?}/$old"
  echo "backup: pruned $old"
done
