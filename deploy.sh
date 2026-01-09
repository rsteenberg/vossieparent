#!/usr/bin/env bash
set -Eeuo pipefail

# ========== CONFIG ==========
PROJECT_DIR="/opt/vossieparent"             # project root containing manage.py
VENV_DIR="$PROJECT_DIR/.venv"               # python venv directory
SERVICE_NAME="vossie.service"               # systemd unit name
APP_PORT="8002"                             # Gunicorn bind port (127.0.0.1:8002)
GIT_REMOTE="${GIT_REMOTE:-origin}"          # remote name
GIT_BRANCH="${GIT_BRANCH:-main}"            # branch to deploy
STATIC_ROOT="${STATIC_ROOT:-$PROJECT_DIR/static_build}"  # must match settings.py STATIC_ROOT
SITE_URL="${SITE_URL:-http://localhost}"    # public URL via Nginx (used for health checks)
# Set to 1 to auto-fix ownership (optional, safe if you know your setup)
FIX_PERMS="${FIX_PERMS:-0}"
PROJECT_USER="${PROJECT_USER:-www-data}"    # expected owner of runtime dirs/files
# Optional Nginx reload after deploy (0=skip, 1=reload)
NGINX_RELOAD="${NGINX_RELOAD:-1}"
NGINX_SERVICE="${NGINX_SERVICE:-nginx}"
# Prefer graceful app reload over hard restart (0=restart, 1=reload)
APP_RELOAD="${APP_RELOAD:-1}"
# Space-delimited list of systemd units for rq workers/scheduler
RQ_WORKER_SERVICES="${RQ_WORKER_SERVICES:-vossie-rq-default.service vossie-rq-mail.service vossie-rqscheduler.service}"
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

reload_nginx_if_enabled() {
  if [ "$NGINX_RELOAD" = "1" ]; then
    log "Reloading Nginx configuration ($NGINX_SERVICE)"
    if command -v nginx >/dev/null 2>&1; then
      if nginx -t; then
        systemctl reload "$NGINX_SERVICE" || warn "Failed to reload $NGINX_SERVICE"
      else
        warn "nginx -t failed; skipping Nginx reload"
      fi
    else
      warn "nginx command not found; cannot reload $NGINX_SERVICE"
    fi
  fi
}

restart_rq_workers() {
  if [ -z "$RQ_WORKER_SERVICES" ]; then
    return
  fi
  for svc in $RQ_WORKER_SERVICES; do
    log "Restarting worker service: $svc"
    systemctl daemon-reload || true
    if ! systemctl restart "$svc"; then
      warn "Failed to restart $svc"
    else
      if ! systemctl is-active --quiet "$svc"; then
        warn "Worker service $svc is not active after restart."
      fi
    fi
  done
}

reload_app_service() {
  local unit="$SERVICE_NAME"
  local exec_reload
  exec_reload=$(systemctl show -p ExecReload --value "$unit" 2>/dev/null || true)
  if [ -z "$exec_reload" ]; then
    warn "ExecReload not defined for $unit. Falling back to restart (no zero-downtime guarantee)."
    systemctl daemon-reload || true
    systemctl restart "$unit"
    return $?
  fi

  # Capture PID before reload to verify behavior
  local pid_before pid_after
  pid_before=$(systemctl show -p MainPID --value "$unit" 2>/dev/null || echo 0)
  log "Reloading service via ExecReload: $unit"
  systemctl daemon-reload || true
  if ! systemctl reload "$unit"; then
    warn "systemctl reload failed; attempting restart"
    systemctl restart "$unit"
  fi
  sleep 2
  systemctl is-active --quiet "$unit" || die "Service not active after reload/restart."
  pid_after=$(systemctl show -p MainPID --value "$unit" 2>/dev/null || echo 0)
  # Informational logging about PID change (depends on ExecReload strategy HUP vs USR2)
  if [ "$pid_before" -eq 0 ] || [ "$pid_after" -eq 0 ]; then
    warn "Could not determine MainPID before/after reload."
  elif [ "$pid_before" -ne "$pid_after" ]; then
    log "Service MainPID changed ($pid_before -> $pid_after): likely zero-downtime USR2 strategy."
  else
    log "Service MainPID unchanged ($pid_after): graceful in-place HUP strategy."
  fi
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
  if [ -n "$RQ_WORKER_SERVICES" ]; then
    echo "  RQ_WORKERS:  $RQ_WORKER_SERVICES"
  else
    echo "  RQ_WORKERS:  (none configured)"
  fi

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

  if [ "$APP_RELOAD" = "1" ]; then
    log "Reload app service (zero-downtime if ExecReload is configured)"
    reload_app_service
  else
    log "Restart service: $SERVICE_NAME (APP_RELOAD=0)"
    systemctl daemon-reload || true
    systemctl restart "$SERVICE_NAME"
    sleep 2
    systemctl is-active --quiet "$SERVICE_NAME" || die "Service not active after restart."
  fi
  systemctl status "$SERVICE_NAME" --no-pager -n 30 || true
  restart_rq_workers

  log "Health checks"
  reload_nginx_if_enabled
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
