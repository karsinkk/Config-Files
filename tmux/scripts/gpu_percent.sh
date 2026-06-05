#!/usr/bin/env sh

if command -v ioreg >/dev/null 2>&1; then
  gpu=$(ioreg -r -d 1 -w 0 -c AGXAccelerator 2>/dev/null \
    | sed -n 's/.*"Device Utilization %"=\([0-9.][0-9.]*\).*/\1/p' \
    | head -n 1)

  if [ -n "$gpu" ]; then
    printf '%s%%' "$gpu"
    exit 0
  fi
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null \
    | awk 'NF { sum += $1; count++ } END { if (count) printf "%.0f%%", sum / count; else printf "n/a" }'
  exit 0
fi

if command -v cuda-smi >/dev/null 2>&1; then
  cuda-smi 2>/dev/null \
    | sed -n 's/.*[[:space:]]\([0-9][0-9]*\)%.*/\1/p' \
    | awk 'NF { sum += $1; count++ } END { if (count) printf "%.0f%%", sum / count; else printf "n/a" }'
  exit 0
fi

printf 'n/a'
