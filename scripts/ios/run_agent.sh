#!/usr/bin/env bash
# Simulator booted: checks blocked hosts, applies the persona's settings,
# installs and launches the app, then hands the simulator to Claude Code.
set -uo pipefail
: "${UDID:?}"
mkdir -p "results/$PERSONA"
for h in $BLOCK_HOSTS; do
  if curl -s -m 6 -o /dev/null "https://$h/"; then echo "$h reachable: aborting"; exit 1; fi
done
xcrun simctl ui "$UDID" appearance "${THEME:-light}"
xcrun simctl ui "$UDID" content_size "${TEXT_SIZE:-large}"
xcrun simctl location "$UDID" set "$GEO" 2>/dev/null || true
xcrun simctl install "$UDID" "$(find app -maxdepth 2 -name '*.app' -type d | head -1)" || { echo "install failed"; exit 1; }
xcrun simctl launch "$UDID" "$APP_ID"; sleep 8
# First capture stores the screen width in points for gesture.sh
python3 scripts/ios/screen.py "$RUNNER_TEMP/warmup" 00 >/dev/null 2>&1 || true
claude -p "Read $BRIEF and personas.json, then do the mission until the final report. PERSONA=$PERSONA PLATFORM=ios APP_ID=$APP_ID. Device: $DEVICE, text size ${TEXT_SIZE:-large}, theme ${THEME:-light}, language $LOCALE. The simulator is already booted and the tools find it on their own (UDID is set): use the commands of the brief directly. Report anything that does not fit this screen (cut text, off-screen buttons, under the notch or home bar, broken layout)." \
  --model "${MODEL:-sonnet}" --max-turns 400 --output-format json \
  --allowedTools "Bash(bash scripts/ios/gesture.sh:*),Bash(python3 scripts/ios/screen.py:*),Bash(python3 scripts/ios/type.py:*),Bash(sleep:*),Bash(ls:*),Bash(cat:*),Bash(mkdir:*),Read,Write,Edit" \
  > results/agent-output.json 2> results/agent-errors.txt
echo "Agent finished (exit $?), $(ls "results/$PERSONA" | wc -l) files"
