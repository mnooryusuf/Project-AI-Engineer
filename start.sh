#!/bin/bash
# start.sh — Skrip untuk menjalankan Agentic RAG (RAM 8GB optimized)
# Usage: ./start.sh [backend|frontend|all]

set -e

# ── Auto-detect Docker path (macOS) ──────────────────────
if ! command -v docker &>/dev/null; then
  if [ -f "/Applications/Docker.app/Contents/Resources/bin/docker" ]; then
    export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
  elif [ -f "$HOME/.docker/bin/docker" ]; then
    export PATH="$HOME/.docker/bin:$PATH"
  fi
fi

# ── Auto-detect Python 3.12 (pyenv) ──────────────────────
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PYENV_ROOT/versions/3.12.7/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

log()    { echo -e "${GREEN}[AGY]${NC} $1"; }
warn()   { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
header() { echo -e "\n${CYAN}══════════════════════════════════════${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${CYAN}══════════════════════════════════════${NC}\n"; }

check_ollama() {
  if ! pgrep -x "ollama" > /dev/null 2>&1; then
    warn "Ollama tidak berjalan. Memulai..."
    brew services start ollama
    sleep 3
  fi
  if ! ollama list > /dev/null 2>&1; then
    error "Ollama gagal dijalankan."
  fi
  log "Ollama ✅"
}

check_models() {
  local models=$(ollama list 2>/dev/null)
  if ! echo "$models" | grep -q "llama3.2:1b"; then
    warn "Model llama3.2:1b belum ada. Mengunduh..."
    ollama pull llama3.2:1b
  fi
  if ! echo "$models" | grep -q "all-minilm"; then
    warn "Model all-minilm belum ada. Mengunduh..."
    ollama pull all-minilm
  fi
  log "Models ✅"
}

start_backend() {
  header "Backend — FastAPI"
  cd "$SCRIPT_DIR/backend"

  # .env dibaca dari root project (lihat backend/config.py), bukan dari sini.
  if [ ! -f "$SCRIPT_DIR/.env" ]; then
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    warn ".env dibuat dari .env.example — harap sesuaikan konfigurasi!"
  fi

  if [ ! -d ".venv" ]; then
    # Dependensi (pydantic-core, psycopg) belum punya wheel untuk Python 3.13+,
    # jadi venv harus dibangun dengan 3.12 — gagal cepat daripada menghasilkan
    # venv rusak yang errornya baru muncul jauh di kemudian hari.
    PY312="$(command -v python3.12 || true)"
    if [ -z "$PY312" ]; then
      error "python3.12 tidak ditemukan. Install dulu: pyenv install 3.12.7"
    fi
    log "Membuat virtual environment dengan $PY312..."
    "$PY312" -m venv .venv
    .venv/bin/pip install -r requirements.txt --quiet
  fi

  log "Menjalankan FastAPI di http://localhost:8000"
  log "API Docs: http://localhost:8000/docs"
  .venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
}

start_frontend() {
  header "Frontend — ViteJS + React"
  cd "$SCRIPT_DIR/frontend"

  if [ ! -d "node_modules" ]; then
    log "Menginstall npm dependencies..."
    npm install --quiet
  fi

  log "Menjalankan React di http://localhost:5173"
  npm run dev
}

main() {
  header "🤖 Agentic RAG — Local AI System"

  # Cek Docker untuk PostgreSQL
  if ! docker ps > /dev/null 2>&1; then
    warn "Docker tidak berjalan. Pastikan Docker Desktop sudah dibuka!"
    warn "Jalankan Docker Desktop, lalu jalankan: docker-compose up -d"
  else
    log "Memastikan PostgreSQL berjalan..."
    cd "$SCRIPT_DIR"
    docker compose up -d 2>&1 | grep -v "^$" || true
    sleep 2
    log "PostgreSQL ✅"
  fi

  check_ollama
  check_models

  MODE="${1:-all}"
  case "$MODE" in
    backend)  start_backend  ;;
    frontend) start_frontend ;;
    all)
      log "Menjalankan Backend + Frontend..."
      start_backend &
      BACKEND_PID=$!
      sleep 3
      start_frontend &
      FRONTEND_PID=$!
      log "Backend PID: $BACKEND_PID | Frontend PID: $FRONTEND_PID"
      log "Tekan Ctrl+C untuk berhenti."
      wait $BACKEND_PID $FRONTEND_PID
      ;;
    *)
      echo "Usage: ./start.sh [backend|frontend|all]"
      exit 1
      ;;
  esac
}

main "$@"
