#!/bin/bash
LOG="$1"; TASK=synthetic; RULES=synthetic
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
cd "$HOME/ted-ops" && /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex exec -m ${CODEX_MODEL:-gpt-6-sol} --skip-git-repo-check "$RULES

TASK: $TASK" > "$LOG" 2>&1
tail -20 "$LOG"
