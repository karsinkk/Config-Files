#!/usr/bin/env sh

if command -v vm_stat >/dev/null 2>&1; then
  page_size=$(vm_stat | awk '/page size of/ {gsub("\\.","",$8); print $8}')
  pages_free=$(vm_stat | awk '/Pages free/ {gsub("\\.","",$3); print $3}')
  pages_inactive=$(vm_stat | awk '/Pages inactive/ {gsub("\\.","",$3); print $3}')
  mem_total=$(sysctl -n hw.memsize 2>/dev/null)

  if [ -n "$page_size" ] && [ -n "$mem_total" ] && [ "$mem_total" -gt 0 ] 2>/dev/null; then
    mem_free=$(( (pages_free + pages_inactive) * page_size ))
    mem_used=$(( mem_total - mem_free ))
    printf '%s%%' $(( mem_used * 100 / mem_total ))
    exit 0
  fi
fi

if command -v free >/dev/null 2>&1; then
  free | awk '/Mem:/ {printf "%d%%", ($3 / $2) * 100}'
  exit 0
fi

printf 'n/a'
