#!/usr/bin/env bash
set -Eeuo pipefail

# ========== CONFIG ==========
PROJECT_DIR="/opt/vossieparent"             # project root containing manage.py
VENV_DIR="$PROJECT_DIR/.venv"               # python venv directory
SERVICE_NAME="vossie.service"               # systemd unit name
APP_PORT="8001"                             # Gunicorn bind port (127.0.0.1:8001)
GIT_REMOTE="${GIT_REMOTE:-origin}"          # remote name
GIT_BRANCH="${GIT_BRANCH:-main}"            # branch to deploy
STATIC_ROOT="${STATIC_ROOT:-$PROJECT_DIR/static_build}"  # must match settings.py STATIC_ROOT
SITE_URL="${SITE_URL:-http://localhost}"    # public URL via Nginx (used for health checks)
# Set to 1 to auto-fix ownership (optional, safe if you know your setup)
FIX_PERMS="${FIX_PERMS:-0}"
PROJECT_USER="${PROJECT_USER:-www-data}"    # expected owner of runtime dirs/files
# ========== END CONFIG ==========

PY="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
GUNICORN="$VENV_DIR/bin/gunicorn"
MANAGE="$PY $PROJECT_DIR/manage.py"

log() { echo -e "\033[1;32m[+] $*\033[0m"; }
warn() { echo -e "\033[1;33m[!] $*\033[0m"; }
die() { echo -e "\033[1;31m[✗] $*\033[0m" >&2; exit 1; }

require_cmd() { command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }

perm_report() {
  local path="$1"
  if [ -e "$path" ]; then
    stat_out=$(stat -c "%A %U:%G %a %n" "$path" 2>/dev/null || true)
    echo "    $(echo "$stat_out")"
  else
    echo "    MISSING: $path"
  fi
}

fix_perms_if_needed() {
  if [ "$FIX_PERMS" = "1" ]; then
    log "Fixing ownership to $PROJECT_USER:$PROJECT_USER on critical paths"
    chown -R "$PROJECT_USER:$PROJECT_USER" "$PROJECT_DIR"
    [ -d "$STATIC_ROOT" ] && chown -R "$PROJECT_USER:$PROJECT_USER" "$STATIC_ROOT"
  fi
}

health_check() {
  local ok=0

  # Gunicorn (direct, localhost)
  if curl -fsS "http://127.0.0.1:${APP_PORT}/accounts/login/" >/dev/null; then
    log "Gunicorn health OK (http://127.0.0.1:${APP_PORT}/accounts/login/)"
  else
    warn "Gunicorn health check failed (direct port)."
    ok=1
  fi

  # Nginx/public
  if curl -fsS "${SITE_URL}/accounts/login/" >/dev/null; then
    log "Public health OK (${SITE_URL}/accounts/login/)"
  else
    warn "Public health check failed (${SITE_URL}/accounts/login/)."
    ok=1
  fi

  return $ok
}

main() {
  require_cmd git
  require_cmd curl
  require_cmd systemctl
  [ -x "$PY" ] || die "Python venv not found at $PY. Create venv and install dependencies."
  [ -x "$PIP" ] || die "pip not found at $PIP"
  [ -d "$PROJECT_DIR/.git" ] || die "PROJECT_DIR is not a git repo: $PROJECT_DIR"

  log "Environment summary"
  echo "  USER:       $(id -un) ($(id -u))"
  echo "  PROJECT_DIR: $PROJECT_DIR"
  echo "  VENV_DIR:    $VENV_DIR"
  echo "  SERVICE:     $SERVICE_NAME"
  echo "  BRANCH:      $GIT_BRANCH"
  echo "  REMOTE:      $GIT_REMOTE"
  echo "  STATIC_ROOT: $STATIC_ROOT"
  echo "  SITE_URL:    $SITE_URL"
  echo "  APP_PORT:    $APP_PORT"

  log "Permission report (no changes yet)"
  perm_report "$PROJECT_DIR"
  perm_report "$VENV_DIR"
  perm_report "$STATIC_ROOT"

  fix_perms_if_needed

  log "Git fetch/pull"
  cd "$PROJECT_DIR"
  # Auto-stash local changes (including compiled .pyc) to avoid merge failures
  git stash push -u -m "deploy.sh auto-stash $(date -u +%F_%T)" || true
  git remote -v || true
  git fetch --all --prune
  git checkout "$GIT_BRANCH"
  git pull --ff-only "$GIT_REMOTE" "$GIT_BRANCH"

  log "Install/upgrade dependencies"
  "$PIP" install --upgrade pip wheel
  "$PIP" install -r requirements.txt

  log "Django migrations"
  $MANAGE migrate --noinput

  log "Collect static"
  mkdir -p "$STATIC_ROOT"
  if ! $MANAGE collectstatic --noinput; then
    warn "collectstatic failed; check STATIC_ROOT in settings.py. Continuing."
  fi

  log "Django checks (deploy)"
  $MANAGE check --deploy || warn "Django deploy checks reported warnings."

  log "Restart service: $SERVICE_NAME"
  systemctl daemon-reload || true
  systemctl restart "$SERVICE_NAME"
  sleep 2
  systemctl is-active --quiet "$SERVICE_NAME" || die "Service not active after restart."
  systemctl status "$SERVICE_NAME" --no-pager -n 30 || true

  log "Health checks"
  if health_check; then
    log "Deployment OK"
    exit 0
  else
    warn "Health checks reported issues. Recent logs:"
    journalctl -u "$SERVICE_NAME" --since "5 minutes ago" --no-pager || true
    exit 1
  fi
}

main "$@"
