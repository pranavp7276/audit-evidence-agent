#!/usr/bin/env bash
# Run by whoever owns the data, after putting the official files in data/raw/.
# Commit the resulting data/CHECKSUMS.sha256 so everyone can `make data-check`.
set -euo pipefail
cd "$(dirname "$0")/../data"
find raw -type f ! -name .gitkeep -print0 | sort -z | xargs -0 sha256sum > CHECKSUMS.sha256
echo "Wrote data/CHECKSUMS.sha256 ($(wc -l < CHECKSUMS.sha256) files). Commit it."
