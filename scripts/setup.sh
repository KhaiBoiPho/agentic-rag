#!/usr/bin/env bash
# setup.sh — First-time environment bootstrap
#
# Usage:
#   bash scripts/setup.sh
#
# What it does:
#   1. Copies .env.example → .env if .env doesn't exist
#   2. Generates cryptographically random secrets for SECRET_KEY and JWT_SECRET_KEY
#   3. Prints next steps

set -euo pipefail
cd "$(dirname "$0")/.."

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"

info()    { echo -e "${GREEN}[setup]${NC} $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
missing() { echo -e "${RED}[error]${NC} $*"; exit 1; }

# ─── Pre-flight checks ────────────────────────────────────────────────────────
command -v docker  >/dev/null 2>&1 || missing "docker is not installed"
command -v openssl >/dev/null 2>&1 || missing "openssl is not installed"

# ─── .env setup ───────────────────────────────────────────────────────────────
if [[ -f .env ]]; then
    warn ".env already exists — skipping copy (delete it and re-run to reset)"
else
    cp .env.example .env
    info "Created .env from .env.example"

    # Generate random secrets
    SECRET_KEY=$(openssl rand -hex 32)
    JWT_SECRET=$(openssl rand -hex 32)

    # Replace placeholder values
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s|change-me-in-production-use-openssl-rand-hex-32|${SECRET_KEY}|g" .env
        sed -i '' "s|change-me-jwt-secret-use-openssl-rand-hex-32|${JWT_SECRET}|g"    .env
    else
        sed -i "s|change-me-in-production-use-openssl-rand-hex-32|${SECRET_KEY}|g" .env
        sed -i "s|change-me-jwt-secret-use-openssl-rand-hex-32|${JWT_SECRET}|g"    .env
    fi
    info "Generated random SECRET_KEY and JWT_SECRET_KEY"
fi

# ─── Fix OPENROUTER_EMBED_MODEL if it still has the wrong default ─────────────
if grep -q "nvidia/llama-nemotron-embed-vl-1b-v2:free" .env 2>/dev/null; then
    warn "OPENROUTER_EMBED_MODEL is set to a vision model — fixing to openai/text-embedding-3-small"
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s|nvidia/llama-nemotron-embed-vl-1b-v2:free|openai/text-embedding-3-small|g" .env
    else
        sed -i "s|nvidia/llama-nemotron-embed-vl-1b-v2:free|openai/text-embedding-3-small|g" .env
    fi
fi

# ─── Remind user about required keys ─────────────────────────────────────────
echo ""
info "Next steps:"
echo "  1. Open .env and fill in the required API keys:"
echo "       OPENROUTER_API_KEY  — https://openrouter.ai/keys"
echo "       FIRECRAWL_API_KEY   — https://firecrawl.dev  (optional, for deep research)"
echo "       ELEVENLABS_API_KEY  — https://elevenlabs.io  (optional, for TTS)"
echo ""
echo "  2. Start the stack:"
echo "       make up"
echo "       # or: docker compose up -d"
echo ""
echo "  3. Open the UI:"
echo "       http://localhost:3210"
echo ""
