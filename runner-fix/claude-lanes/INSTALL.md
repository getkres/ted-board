# Combined runtime installation

Use [RECONCILER.md](../RECONCILER.md) for the reviewed mini-only cutover, backups, reconstruction, tests, durable enable gate, and rollback. This branch folds the current PR 40 lane changes into the reconciler. Install the combined candidate once. Do not stack the older PR 40 runtime patch over it.

The standalone runtime.patch remains available for offline compatibility testing against the recorded live source. It creates claude_lanes.py, runner_admission.py, and capacity.json, and patches sessions.py and session_worker.py. Both variants use the same capacity reader and configuration. It is not a second installation step.

Keep the lane flag false during cutover. Account setup and activation remain separate Ted actions in [SETUP.md](SETUP.md). No login, flag change, routine, service restart, runtime installation, SQL execution, or deployment is performed by this preparation job.
