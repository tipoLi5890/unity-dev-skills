# GPU scheduling and model lifetime

## Invariants

1. Keep one running or pending workflow at a time.
2. Poll `/history/{prompt_id}` to a terminal state before the next submission.
3. Same model family: keep it loaded between consecutive known jobs.
4. Different model family: empty queue → `/free` → submit the next job.
5. No known next job: empty queue → `/free`.

The queue is empty only when both `queue_running` and `queue_pending` have length
zero. Never unload while either array contains an item.

```text
H3 FL2VA A → wait → H3 FL2VA B → wait
→ empty queue → unload/free
→ H3 REF2VA A → wait
→ empty queue → unload/free
→ MiniMax Music 3 A → wait → empty queue → unload/free
```

Do not pre-submit a whole batch. Sequential submission prevents a model-family
switch or cleanup from racing the next job.

## Model-family identity

- H3 T2V and I2V use the FL2VA diffusion model and may share one loaded model.
- H3 R2V and multi-frame reference use the REF2VA diffusion model and may share
  one loaded model.
- MiniMax Music 3 and Stable Audio 3 are separate families.
- Common VAE or text-encoder filenames do not make two jobs the same family.

## Recovery

- Validation failure: correct the graph once or report the missing model.
- Runtime failure: wait for the queue to settle, then unload unless a same-model
  retry was explicitly chosen.
- Lost WebSocket: use `/history` and `/queue` as authoritative polling sources.
- `/free` can return before VRAM telemetry settles. Read `/system_stats` once more;
  do not loop indefinitely for a particular free-VRAM value.
