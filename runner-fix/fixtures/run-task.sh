#!/bin/bash
# contract fixture
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
if [[ -n "${FICTORA_COMPANY_DB:-}" ]]; then
  exec python3 "$COORDINATOR" --db "$FICTORA_COMPANY_DB" run-opus "$TASK_ID" --repo "$REPO" --timeout 120
fi
exec python3 "$COORDINATOR" run-opus "$TASK_ID" --repo "$REPO" --timeout 120
