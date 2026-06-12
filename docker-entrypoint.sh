#!/bin/sh
# Supervise the bundled mock LLM (:8001) + the agent backend (:8000).
# POSIX sh (the slim image has no bash -> no `wait -n`). Docker/Linux only: uses /proc.

# Install the signal handler BEFORE starting children so an early SIGTERM can't
# orphan them.
shutting_down=0
term() {
  shutting_down=1
  kill "$mock_pid" "$server_pid" 2>/dev/null
}
trap term TERM INT

python /app/llm/src/custom_llm_server.py &
mock_pid=$!

python /app/server/src/server.py &
server_pid=$!

# A PID is "alive" only if /proc/PID exists and its state is not Z (zombie).
alive() {
  [ -d "/proc/$1" ] || return 1
  st=$(awk '/^State:/ { print $2; exit }' "/proc/$1/status" 2>/dev/null)
  [ -n "$st" ] && [ "$st" != "Z" ]
}

while alive "$mock_pid" && alive "$server_pid"; do
  sleep 1
done

# Stop whichever child is still running.
kill "$mock_pid" "$server_pid" 2>/dev/null

# If the loop ended because a child crashed (not a SIGTERM/SIGINT), exit non-zero
# so restart policies / orchestrators react.
if [ "$shutting_down" -eq 0 ]; then
  echo "docker-entrypoint: a supervised process exited unexpectedly" >&2
  exit 1
fi
exit 0
