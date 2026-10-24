# Research: preventing silent stalls at Ted Board scale

Researched on October 23, 2026, from primary sources. Scope: one Mac mini, one human operator, and dozens of agents. This is research and a recommendation, not an implementation or authorization to deploy, spend, send messages, change routines, or write to a database.

## Recommendation

Build the smallest useful reconciler around the existing board and evidence, borrowing mature systems' invariants before adopting their platforms. Persist the intended outcome, independently observe actual progress, evaluate deadlines even when an agent never returns, and select a bounded next action. A status string, process heartbeat, or agent's claim of completion is insufficient evidence that the intended outcome happened.

The strongest directly applicable warning comes from Airflow's own SLA migration guide: its older SLA approach checked when a DAG run finished, so a run that never finished never triggered that check. Its Deadline Alerts instead store an expiry and let the scheduler evaluate it independently. The local adaptation is a sweep of all unfinished obligations, including queued, blocked, waiting, and running work. [Airflow SLA-to-deadline migration](https://airflow.apache.org/docs/apache-airflow/3.1.8/howto/sla-to-deadlines.html)

This recommendation is an inference from the sources below. None establishes Ted Board's present failure rate, proves the existing runtime safe to retry, or quantifies the benefit of a platform migration.

## Patterns, primary evidence, and one idea to steal

### 1. Temporal: durable execution and recorded recovery

**Evidence and age.** Current Temporal documentation describes a durable event history that lets a worker reconstruct workflow state after a crash. Workflow code must support deterministic replay; failure-prone operations, API calls, and LLM calls belong in Activities. Activity retries are normally enabled, while a Workflow Execution does not have a retry policy by default. Heartbeat timeouts detect missing Activity heartbeats and can trigger policy-controlled retries. [Event History](https://docs.temporal.io/encyclopedia/event-history), [Retry Policies](https://docs.temporal.io/encyclopedia/retry-policies), and [Detecting Activity failures](https://docs.temporal.io/encyclopedia/detecting-activity-failures)

**Steal at this scale.** Preserve a small durable record of every attempt, checkpoint, result, and next eligible action. Resume from verified checkpoints after a worker disappears. Separate worker liveness from evidence of useful progress.

**Cost and uncertainty.** This borrows the recovery model, not Temporal's replay guarantee. A homegrown log needs deliberate crash consistency. Adopting Temporal also requires workflow boundaries, Activity design, deterministic workflow code, and operational familiarity. It cannot infer whether an opaque agent's answer is useful or whether an external side effect happened.

### 2. AWS Step Functions: explicit timeouts, retry policies, and fallback states

**Evidence and age.** Current AWS documentation offers task timeouts, heartbeat timeouts, bounded retries, exponential backoff, jitter, and fallback transitions. Standard Workflows retain durable, auditable execution state and use an exactly-once workflow execution model unless explicit retries apply. This model should not be generalized into a guarantee about arbitrary external effects during retries. [Workflow types](https://docs.aws.amazon.com/step-functions/latest/dg/choosing-workflow-type.html), [Task state](https://docs.aws.amazon.com/step-functions/latest/dg/state-task.html), and [Error handling](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html)

**Steal at this scale.** Give each stage an explicit deadline and failure transition: retry if safe, wait for a named dependency, or require intervention. Make exhausted retries a visible state with a next owner and action.

**Cost and uncertainty.** State-machine clarity is inexpensive to borrow. An AWS migration introduces integration, identity, logs, billing, and worker coordination. An indefinitely generous default timeout does not protect against silent stalls; deadlines must be configured for the work.

### 3. Airflow: independent deadlines and cheap waiting

**Evidence and age.** Airflow 3 removed legacy SLAs in favor of Deadline Alerts. The current stable documentation served Airflow 3.3.2 during research and still labels Deadline Alerts experimental. A deadline has a reference, interval, and callback. Deferrable operators release worker capacity while waiting, rather than occupying a slot doing no useful work. [Upgrade guide](https://airflow.apache.org/docs/apache-airflow/stable/installation/upgrading_to_airflow3.html), [Deadline Alerts](https://airflow.apache.org/docs/apache-airflow/stable/howto/deadline-alerts.html), and [Deferrable operators](https://airflow.apache.org/docs/apache-airflow/stable/authoring-and-scheduling/deferring.html)

**Steal at this scale.** Model waiting explicitly, with `waiting_for`, `next_check_at`, and a deadline that exists before work begins. A blocked dependency or human approval should not occupy an active agent slot, erase age, or suppress deadline evaluation.

**Cost and uncertainty.** This needs disciplined state updates and dependency identities. Installing Airflow merely to get this behavior adds scheduler and triggerer operations. Experimental deadline APIs and older SLA examples must not be treated as interchangeable.

### 4. Kubernetes: desired versus actual state, evaluated repeatedly

**Evidence and age.** Current Kubernetes documentation defines controllers as loops that move actual state toward desired state. Its API conventions explicitly favor level-based behavior: current desired state matters even when intermediate changes were missed. This is an established architectural concept documented in current sources, not a claim that Kubernetes continuously polls every object. [Controllers](https://kubernetes.io/docs/concepts/architecture/controller/) and [API conventions, Spec and Status](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md#spec-and-status)

**Steal at this scale.** Treat a board card as an obligation to reach a verifiable outcome. On each sweep, compare that obligation with current worker ownership, dependency state, and evidence. Event hooks can wake the loop quickly; a periodic full sweep catches forgotten work and missed hooks.

**Cost and uncertainty.** A small loop is sufficient. Kubernetes itself is unnecessary at this scale. Reconciliation must be repeatable, use one authoritative identity per obligation, and avoid interpreting every old card as permission to start new work.

### 5. Chubby: leases, uncertainty, and fencing stale owners

**Evidence and age.** Google's Chubby paper is a historical 2006 design, not current product documentation. It describes renewable session leases, a jeopardy period when ownership becomes uncertain, and sequencers that let recipients reject stale lock holders. The receiver must enforce the sequencer. [Original paper, sections 2.4 and 2.8](https://storage.googleapis.com/gweb-research2023-media/pubtools/4444.pdf), [Google Research publication record](https://research.google/pubs/the-chubby-lock-service-for-loosely-coupled-distributed-systems/)

**Steal at this scale.** Claim work with an expiring lease and increasing attempt generation. Require the current generation when accepting checkpoints and completion. An old worker waking after a pause must not overwrite a replacement's result.

**Cost and uncertainty.** Lease expiry does not prove the old process stopped. A generation checked only in board writes cannot fence an email, purchase, or remote API that ignores it. Ambiguous external effects need read-only verification or human review before replay. A one-machine lease also does not provide Chubby's distributed availability.

### 6. SQS visibility timeout: abandoned claims become eligible again

**Evidence and age.** Current SQS documentation makes received messages temporarily invisible. If a consumer does not delete a message before visibility expires, it becomes eligible for another consumer. Consumers can extend visibility while working. AWS also warns that expiry can lead to duplicate processing. [Visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html) and [Outage recovery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/designing-for-outage-recovery-scenarios.html)

**Steal at this scale.** Replace permanent ownership with a renewable claim. After expiry, classify the abandoned attempt, check for late completion evidence, and make only safe work eligible for a new attempt. Keep the original obligation and age intact.

**Cost and uncertainty.** A short lease detects loss quickly but risks false abandonment during pauses, sleep, or network failures. A long lease delays recovery. Heartbeat-based extensions should be paired with an independent progress deadline so a live but unproductive process cannot renew forever.

### 7. SQS dead-letter queues and redrive: quarantine is recoverable work

**Evidence and age.** Current SQS guidance routes repeated failures into a DLQ using `maxReceiveCount`, retaining them for diagnosis. Redrive moves messages back for processing and supports controlled velocity. Redriven messages receive new message identifiers and enqueue times, which makes preserving business identity separately important. [DLQs](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html) and [DLQ redrive](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html)

**Steal at this scale.** Quarantine repeated failures with the original card ID, first-start time, failure evidence, attempted remedies, named owner, and a concrete release condition. Permit a controlled retry only after that condition changes. Quarantine is visible unfinished work, not completion.

**Cost and uncertainty.** A DLQ can become another silent backlog. It needs an age view and a review deadline. Redrive without a fix, bounded volume, or idempotency can reproduce the same failure or duplicate effects.

### 8. Idempotency, bounded exponential backoff, and jitter

**Evidence and age.** Amazon's Builders' Library explains that a timeout does not establish that a side effect failed. Caller-supplied request identifiers distinguish repeated delivery of the same intent from a new intent. Its backoff article was published in 2019; the current Well-Architected guidance continues to recommend jitter, retry limits, and avoiding compounded retries at multiple layers. [Idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/), [Timeouts and backoff](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/), and [Retry limits](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_mitigate_interaction_failure_limit_retries.html)

**Steal at this scale.** Assign a stable intent key to each side effect. Retry only classified transient failures, at one responsible layer, with capped attempts and elapsed time. Spread retries with jitter. Preserve the key across replacement workers.

**Cost and uncertainty.** A local deduplication record cannot make a remote action idempotent unless the remote system supports a key or exposes reliable evidence for reconciliation. Authentication failures, missing permission, invalid input, and unmet approval requirements usually need a state change, not more retries.

### 9. Kanban: control WIP and show the age of unfinished work

**Evidence and age.** The current Kanban Guide is May 2025, rather than the commonly linked 2020 editions. It calls for explicit WIP control, active unblocking, and four flow measures: WIP, throughput, work-item age, and cycle time. An SLE expresses a completion-time forecast. ProKanban's September 2025 practitioner article shows an aging-WIP chart with age versus SLE bands. The guide is the normative source; the chart article is first-party practitioner guidance, not evidence from a controlled experiment. [Kanban Guide](https://kanbanguides.org/the-kanban-guide/2025.5/) and [Visualizing flow metrics](https://prokanban.org/blog/visualizing-flow-metrics---where-to-begin)

**Steal at this scale.** Show unfinished cards by age and workflow stage, with separate blocked reasons. Review the oldest and most valuable obligations first. Limit work entering active execution and human review according to actual capacity, rather than available agent count.

**Cost and uncertainty.** No purchased charting product is required. An initial SLE is a hypothesis until enough comparable completed work exists. Mixing tiny scripts and multi-day business decisions in one percentile produces misleading thresholds. A chart needs an action policy to change outcomes.

### 10. Google SRE: alert on consequential symptoms and measure toil

**Evidence and age.** Google's 2016 SRE book distinguishes symptoms from causes and emphasizes actionable paging. Its 2018 workbook advocates measuring repetitive operational work and removing its source. These are older, still published operating concepts, not a current service guarantee. Google's institutional 50% operational-work limit is context for Google, not a suitable default target for this operation. [Monitoring distributed systems](https://sre.google/sre-book/monitoring-distributed-systems/), [Eliminating toil](https://sre.google/sre-book/eliminating-toil/), and [Workbook](https://sre.google/workbook/eliminating-toil/)

**Steal at this scale.** Make the principal symptom “a valuable obligation has no credible next action or is missing its promised outcome.” Use missing heartbeats, repeated errors, and absent dependencies to diagnose it. Track human minutes spent checking, restarting, and chasing agents, then remove the most repetitive cause.

**Cost and uncertainty.** A dashboard alone still requires someone to inspect it. Excessive notifications consume the only human's capacity. Successful automatic retries are useful telemetry, but generally do not deserve an interruption.

### 11. Escalation ladders: recovery, accountable intervention, and acknowledgment

**Evidence and age.** Google's published on-call guidance describes acknowledgment, triage, and escalation, with primary and secondary coverage in many teams. Its incident-management guidance emphasizes timely, actionable, user-facing alerts. These sources support a response ladder, but they do not prescribe a universal number of minutes. [Being on-call](https://sre.google/sre-book/being-on-call/) and [Incident-management guide](https://sre.google/resources/practices-and-processes/incident-management-guide/)

**Steal at this scale.** Use a ladder of evidence inspection, one bounded safe recovery, a consolidated human decision item, and an urgent alert only for time-sensitive material impact. Every rung needs a deadline and an acknowledgment or resolution state. Since there is one human, an unacknowledged alert should preserve evidence and pause unsafe dependent work; creating more agent supervisors does not create a second human responder.

**Cost and uncertainty.** No new notification channel or message is authorized by this report. Existing approved channels and quiet hours would need to govern any implementation. Deduplicate related stalls into one incident so a single dependency outage does not generate dozens of separate demands.

## Minimal synthesis for a later design

The following is a proposed contract, not a claim about the existing schema or code:

| Concern | Minimum record or rule | Why it matters |
| --- | --- | --- |
| Intent | Stable obligation ID, desired outcome, priority, and completion evidence rule | Preserves what must happen across worker changes |
| Ownership | Attempt ID, owner, generation, and lease expiry | Makes abandoned ownership visible and rejects stale completion |
| Liveness | Last worker heartbeat | Detects missing workers |
| Progress | Last verified checkpoint and expected next evidence | Detects workers that are alive but stuck |
| Waiting | Named dependency or human decision, next check, and deadline | Keeps waiting explicit and accountable |
| Recovery | Error class, retry count, next eligible time, and idempotency or ambiguity classification | Bounds recovery and avoids blind replay |
| Escalation | Incident key, severity, last escalation, acknowledgment, and next deadline | Prevents duplicate noise and forgotten intervention |
| Completion | Verified artifact or result pointer and validation outcome | Stops optimistic status updates from closing unfinished work |
| Reconciler health | Last completed sweep, evaluated count, and oldest unevaluated obligation | Exposes a stalled supervisor |

Keep observation separate from action selection. A first version should produce a dry-run decision list with evidence, reason, and proposed action. It should not automatically replay uncertain side effects, infer approval from silence, reopen intentionally canceled work, or mark a card complete merely because a worker exited. The purpose of the safety boundary is concrete: retries and replacements can duplicate effects even when the underlying failure signal is real.

Choose thresholds from observed work classes. Queue age, time without progress, lease expiry, dependency waiting time, human acknowledgment time, and business due time answer different questions. A single “stale after N minutes” rule cannot represent all of them. A monitor on the same Mac mini cannot report a total mini outage while that mini is unavailable. Launchd supervision and a durable sweep watermark improve recovery and diagnosis, but only an independent observer can detect that host's absence in real time. These are engineering deductions, not availability claims from the sources.

## Costs, sequencing, and uncertainty

| Approach | Direct cost evidence | Main cost or uncertainty | Recommendation |
| --- | --- | --- | --- |
| Small local reconciler using existing capacity | No new service purchase is intrinsically required | Engineering time, state quality, crash consistency, false positives, and one-host failure domain | Start with read-only classification and evidence quality |
| Temporal Cloud | Current page lists no base monthly fee and starts at $50 per million actions, plus active and retained storage, with developer support priced at 10% of usage | Actual action and storage volume, worker integration, and support terms need an estimate | Reconsider when durable multi-step recovery consumes more effort than integration |
| Step Functions Standard | Current page bills state transitions, includes 4,000 free transitions per month, and charges retries as transitions | Region-specific rates, worker compute, logging, and cross-service integration | Prefer if the workflows already center on AWS and explicit state machines |
| Self-managed workflow or cluster platform | No price estimate is asserted here | Installation, upgrades, persistence, backups, monitoring, and operating expertise | Avoid adopting Airflow, Kubernetes, or a new distributed lock service solely for this problem |

Pricing references were checked on October 23, 2026: [Temporal pricing](https://temporal.io/pricing) and [Step Functions pricing](https://aws.amazon.com/step-functions/pricing/). These are service pricing facts, not quotes for this workload. No account, trial, subscription, or paid resource was created.

Sequence the work as: establish a reliable inventory and completion evidence; classify stalls in dry run; compare findings against human judgment; then propose narrowly bounded recovery for demonstrably idempotent work. Expand only after measuring detection usefulness, missed stalls, repeat failures, duplicate-action incidents, review backlog age, and human intervention minutes. No universal implementation-time estimate is credible without inspecting the current runtime and data quality.

The contribution toward the standing $10–15M retirement objective is indirect and uncertain: recover human time, reduce avoidable operational loss, and help valuable work finish. Agent activity, recovered cards, revenue, and company valuation are not retirement assets. Evaluate the first version by measured human time saved and verified business outcomes, then compare those gains with maintenance time and any platform bill. Avoid building a new operations platform whose upkeep exceeds the stalls it prevents.

## Source freshness and evidence limits

- Current operational documentation: Temporal, AWS Step Functions, SQS, Kubernetes, and Airflow documentation, checked on October 23, 2026. Stable URLs may change versions or behavior after this date.
- Versioned practice reference: Kanban Guide, May 2025. Earlier 2020 editions should not be presented as its current wording.
- Historical architectural evidence: Chubby, 2006; Google SRE book, 2016; SRE workbook, 2018; and Amazon's backoff article, 2019. Their concepts remain useful, but they are not evidence of current product features or prices.
- Local recommendations are explicitly synthesized for this scale. This research did not inspect production traces, estimate current stall incidence, test clock or crash behavior, validate a schema, or establish safe replay of any existing agent task.
