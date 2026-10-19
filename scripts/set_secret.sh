#!/usr/bin/env bash
# Store a secret as a locked-down file and point the app at it.
#
#   scripts/set_secret.sh GMAIL_APP_PASSWORD [--restart]
#
# What it does, in order:
#   1. Asks for the value with hidden input (never as an argument, never in
#      shell history, never echoed). Piped input also works: `... | set_secret.sh NAME`.
#   2. Writes it to $SECRETS_DIR/<name> (mode 600, directory 700), keeping the
#      previous value as <name>.prev.
#   3. Verifies the new value actually works (for GMAIL_APP_PASSWORD: a real
#      SMTP login, nothing is sent). If that fails, the old value is put
#      back and nothing else changes.
#   4. Only then: sets <NAME>_FILE=<path> in .env and removes any plain
#      <NAME>=... line, so the secret no longer sits in .env.
#   5. With --restart, restarts the backend LaunchDaemon (asks for sudo).
#
# Overridable: SECRETS_DIR, ENV_FILE, PYTHON, SERVICE_LABEL, VERIFY_CMD.
set -euo pipefail
umask 077

die() { echo "ERROR: $*" >&2; exit 1; }

NAME="${1:-}"
RESTART=false
[[ "${2:-}" == "--restart" ]] && RESTART=true
[[ "$NAME" =~ ^[A-Z][A-Z0-9_]*$ ]] || die "usage: $0 SECRET_NAME [--restart]   (e.g. GMAIL_APP_PASSWORD)"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
SECRETS_DIR="${SECRETS_DIR:-$HOME/.config/zybrannox/secrets}"
PYTHON="${PYTHON:-$ROOT/venv/bin/python}"
SERVICE_LABEL="${SERVICE_LABEL:-system/com.zybrannox.billing.backend}"
TARGET="$SECRETS_DIR/$(echo "$NAME" | tr '[:upper:]' '[:lower:]')"

[[ -f "$ENV_FILE" ]] || die "$ENV_FILE not found"
[[ -x "$PYTHON" ]] || die "Python not found at $PYTHON (set PYTHON=...)"

# Check for a verifier before touching anything.
VERIFY_CMD="${VERIFY_CMD:-}"
if [[ -z "$VERIFY_CMD" && "$NAME" == "GMAIL_APP_PASSWORD" ]]; then
  VERIFY_CMD="$PYTHON -m scripts.check_email_credentials"
fi

# --- 1. read the value -------------------------------------------------------
if [[ -t 0 ]]; then
  read -rsp "Enter new $NAME (hidden): " secret; echo
  read -rsp "Enter it again to confirm: " again; echo
  [[ "$secret" == "$again" ]] || die "the two entries don't match"
  unset again
else
  read -r secret || true
fi
secret="${secret//[[:space:]]/}"   # Google displays app passwords in groups of four
[[ -n "$secret" ]] || die "no value entered"

# --- 2. write it, keeping the previous one -----------------------------------
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"
HAD_PREVIOUS=false
if [[ -f "$TARGET" ]]; then
  cp -p "$TARGET" "$TARGET.prev"
  HAD_PREVIOUS=true
fi
tmp="$(mktemp "$SECRETS_DIR/.tmp.XXXXXX")"
printf '%s' "$secret" > "$tmp"
chmod 600 "$tmp"
mv "$tmp" "$TARGET"            # atomic: a reader never sees a half-written file
unset secret

rollback() {
  if $HAD_PREVIOUS; then mv "$TARGET.prev" "$TARGET"; else rm -f "$TARGET"; fi
}

# --- 3. verify BEFORE switching anything over --------------------------------
if [[ -n "$VERIFY_CMD" ]]; then
  echo "Verifying the new value..."
  if ! (cd "$ROOT" && env "${NAME}_FILE=$TARGET" $VERIFY_CMD); then
    rollback
    die "verification failed - the previous value was restored and nothing else was changed."
  fi
else
  echo "(No verifier for $NAME - stored, but not tested.)"
fi

# --- 4. point .env at the file; drop the plain-text value --------------------
"$PYTHON" - "$ENV_FILE" "$NAME" "$TARGET" <<'PY'
import os, re, sys, tempfile
path, name, target = sys.argv[1:4]
lines = open(path).read().splitlines()
kept = [l for l in lines if not re.match(rf"\s*{re.escape(name)}\s*=", l) and not re.match(rf"\s*{re.escape(name)}_FILE\s*=", l)]
kept.append(f"{name}_FILE={target}")
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".")
with os.fdopen(fd, "w") as f:
    f.write("\n".join(kept) + "\n")
os.chmod(tmp, 0o600)
os.replace(tmp, path)
PY
rm -f "$TARGET.prev"
echo "OK: $NAME is now read from $TARGET (mode 600); the plain value was removed from $(basename "$ENV_FILE")."

# --- 5. restart --------------------------------------------------------------
if $RESTART; then
  echo "Restarting $SERVICE_LABEL (sudo)..."
  sudo launchctl kickstart -k "$SERVICE_LABEL"
  echo "Restarted."
else
  echo "Restart the backend to apply:  sudo launchctl kickstart -k $SERVICE_LABEL"
fi
echo "Reminder: revoke the OLD value at its source (Google Account > Security > App passwords)."
