#!/usr/bin/env bash
# Start the migrated dashboard with the project root available to the app.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export POLY_ARB_ROOT="${POLY_ARB_ROOT:-$ROOT}"

cd "$ROOT/dashboard"
exec npm run dev
