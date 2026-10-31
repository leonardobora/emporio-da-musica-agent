#!/usr/bin/env bash
# Regenerate src/emporio/policies.txt from the PDF (requires poppler-utils).
set -euo pipefail
cd "$(dirname "$0")/.."
pdftotext -layout "data/políticas_da_loja.pdf" src/emporio/policies.txt
echo "wrote src/emporio/policies.txt ($(wc -c < src/emporio/policies.txt) bytes)"
