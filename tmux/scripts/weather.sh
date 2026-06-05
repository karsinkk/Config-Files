#!/usr/bin/env sh

location="$*"
cache_dir="${TMPDIR:-/tmp}/tmux-weather"
safe_location=$(printf '%s' "$location" | tr -c 'A-Za-z0-9._-' '_')
[ -n "$safe_location" ] || safe_location="auto"
cache_file="$cache_dir/${safe_location}-temp.txt"
ttl_seconds=900

mkdir -p "$cache_dir" 2>/dev/null || true

now=$(date +%s)
if [ -f "$cache_file" ]; then
  mtime=$(stat -f %m "$cache_file" 2>/dev/null || stat -c %Y "$cache_file" 2>/dev/null || printf 0)
  if [ $((now - mtime)) -lt "$ttl_seconds" ]; then
    cat "$cache_file"
    exit 0
  fi
fi

if command -v curl >/dev/null 2>&1; then
  if [ -n "$location" ]; then
    encoded=$(printf '%s' "$location" | sed 's/ /%20/g')
    weather=$(curl -m 2 -fsS "https://wttr.in/$encoded?format=%t" 2>/dev/null)
  else
    weather=$(curl -m 2 -fsS "https://wttr.in/?format=%t" 2>/dev/null)
  fi

  if [ -n "$weather" ]; then
    printf '%s\n' "$weather" > "$cache_file"
    printf '%s' "$weather"
    exit 0
  fi
fi

if [ -f "$cache_file" ]; then
  cat "$cache_file"
else
  printf 'n/a'
fi
