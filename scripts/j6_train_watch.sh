#!/bin/bash
# J6: cycles of training + quick deterministic check (sync x10, 1 episode) of the latest checkpoint.
# Stops early when the deterministic time is below the D30 threshold. Log: runs/j6/<run>-det.jsonl
# usage: scripts/j6_train_watch.sh runs/j4/<run> [cycle_s] [max_cycles] [threshold_ms]
RUN=$1; CYCLE=${2:-2400}; MAX=${3:-12}; THR=${4:-24230}
cd "$(dirname "$0")/.."
NAME=$(basename "$RUN"); LOG=runs/j6/$NAME-det.jsonl
for c in $(seq "$MAX"); do
  sleep "$CYCLE"
  uv run python scripts/tm.py stop --run "$RUN" >/dev/null
  for i in $(seq 90); do grep -q '"phase": "running"' "$RUN/status.json" || break; sleep 2; done
  CK=$(python3 -c "import json;print(json.load(open('$RUN/checkpoints/latest.json'))['dir'].split('/')[-1])")
  R=$(timeout 600 uv run python scripts/tm.py eval --run "$RUN" --checkpoint "$CK" --episodes 1 --mode sync --speed 10 --first-episode $((620000 + c * 10)) 2>/dev/null | grep '"episode"' | head -1)
  [ -z "$R" ] && R=null
  echo "{\"cycle\": $c, \"checkpoint\": \"$CK\", \"time\": \"$(date +%T)\", \"result\": $R}" | tee -a "$LOG"
  MS=$(echo "$R" | python3 -c "import json,sys;d=json.loads(sys.stdin.read()) or {};print(d.get('race_ms') if d.get('status')=='finished' else 999999)")
  if [ "$R" = null ]; then echo "eval failed (game down?); stopping the watch"; exit 1; fi
  if [ "$MS" -lt "$THR" ]; then echo "below threshold: $CK $MS"; exit 0; fi
  setsid nohup uv run python scripts/tm.py resume --run "$RUN" --until-stopped >> runs/j6/train-$NAME.log 2>&1 < /dev/null &
  sleep 20
done
