#!/usr/bin/env bash
# Descarga los datasets de la semana 1 (no se versionan: input.txt pesa 1 MB).
set -euo pipefail
cd "$(dirname "$0")"
curl -fL -o names.txt https://raw.githubusercontent.com/karpathy/makemore/master/names.txt
curl -fL -o input.txt https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt
wc -l names.txt input.txt
