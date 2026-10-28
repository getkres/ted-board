#!/bin/bash
LOG="$1"
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
# contract fixture padding
perl -e 'alarm 5400; exec @ARGV' /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex exec -m gpt-6-sol \
  --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -C "$HOME/Claude Code - Fictora" \
  "Headless scheduled run on the Mac mini (no human watching, Sebastian is traveling). Never ask for approval. Same hard lines as Ted: no purchases, no spending, no posting/sending anything external unless the prompt below explicitly makes that routine part of the job. $PROMPT" >> $LOG 2>&1
print "$(date '+%F %T') exit $?" >> $LOG
