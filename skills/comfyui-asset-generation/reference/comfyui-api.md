# ComfyUI HTTP API

Use a server URL without a trailing slash, such as `http://host:port`.

Resolve the URL in this order:

1. CLI `--server`
2. `COMFYUI_SERVER_URL`
3. `~/.codex/comfyui-asset-generation/config.json`

Local configuration schema:

```json
{
  "server_url": "http://private-host:port",
  "max_concurrent_jobs": 1,
  "unload_when_idle": true
}
```

The configuration is machine-local and may contain a private address. Do not
copy it into a reusable skill template or user deliverable. From Claude Code the
usual route is `COMFYUI_SERVER_URL` (or the user pastes the URL in the
conversation and it is passed as `--server`); the address never goes into a
repo, a doc, a script default or a commit message.

| Purpose | Request |
|---|---|
| Health, versions, GPU and VRAM | `GET /system_stats` |
| Running and pending jobs | `GET /queue` |
| Node definitions and model choices | `GET /object_info` or `/object_info/{class}` |
| Submit an API-format graph | `POST /prompt` |
| Read job state and outputs | `GET /history/{prompt_id}` |
| Download output | `GET /view?filename=...&subfolder=...&type=output` |
| Upload an input | `POST /upload/image` with multipart `image`, `type=input`, and optional `overwrite`; video and audio inputs use this same endpoint and field name |
| Unload models and clear cached memory | `POST /free` |

Submission body:

```json
{"client_id":"unique-client-id","prompt":{"1":{"class_type":"...","inputs":{}}}}
```

Cleanup body, sent only after both queue arrays are empty:

```json
{"unload_models":true,"free_memory":true}
```

`/free` may return an empty body. Treat any successful 2xx response as success;
do not require JSON.

## Client overrides and output

`scripts/comfy_asset_client.py` takes a template and changes it per run:

```bash
--set 186.target_face_count=8000        # NODE.INPUT=VALUE, repeatable
--set 122.image=pickup_crate.png        # not JSON, so a string
--set '312.masks=["122",1]'             # a JSON list rewires the input to node 122, output 1
--set 4.caption=@captions/menu.txt      # @path: the value is the file's text, line breaks kept
```

VALUE is parsed as JSON when it parses (numbers, booleans, lists) and is a string
otherwise; quote a value that must stay a string of digits (`'119.resolution="64"'`).
A node id that is not in the graph is an error. Dynamic-combo inputs use dotted
names after the first dot: `--set 241.sign_mode.qef=false`.

The client refuses to submit while any input still contains `REPLACE_WITH_`, and
while the queue holds a running or pending job. An upload keeps its local
basename. Without `--overwrite-uploads`, a server that already holds a different
file of that name stores the new one as `name (1).png`, and a graph input naming
`name.png` reads the old file with no error; the client then warns on stderr.
Name uploads per asset, view and run (`runner_front_r03.png`).

```bash
--server-label studio-gpu               # the machine's name, recorded instead of its address
--job-log jobs.jsonl                    # one JSON line per run, success or failure
```

Its JSON result adds `elapsed_seconds` and `vram_free_min`, the lowest free VRAM
seen while polling, to `prompt_id`, `uploads`, `outputs` and `vram_after_unload`,
then what pins the run for skill `art-asset-registry`: `workflow_sha256`,
`workflow_name` (the file name only), `overrides` (each `--set` target with its
value: a number, boolean, null or `["node", slot]` link as it is; any text, list
or object as `sha256:` plus the first 12 hex characters of its hash, so a prompt
or a key is never printed there), `server_label` (`null` without the flag), `output_files` (each
download with its `sha256` and `bytes`; `outputs` stays a list of paths) and
`record`, the partial ledger record. Each `uploads` entry gains the local file's
`sha256`.

No server address is written to the result or to the job log, and a
`--server-label` holding `://` is refused. A log line is the result plus `ts` and
`exit_code`; a failed run's line has `exit_code` 1, its `error` with the address
and any URL replaced, the same pinning keys, and a `record` whose verdict is
`failed` once the graph was submitted, `harness` before. In every log line each
`--set` text, and each graph text holding whitespace (a prompt, a caption), is
replaced by its short hash wherever it appears, so a server error that quotes
the graph back does not carry the prompt into the log. A failure still prints
its reason, unredacted, to stderr and exits 1.

Before changing a knob, compare the graph with the official template:
`scripts/graph_diff.py OFFICIAL.json PROJECT.json` (`reference/image-to-3d-tuning.md`).

## Saved workflows

List server-side workflows with:

```text
GET /api/userdata?dir=workflows&recurse=true
```

For `/userdata/{file}`, encode a nested path as one parameter, for example
`workflows%2Fexample.json`. A saved UI workflow is not automatically an API graph;
expand subgraphs or export it in API format before submitting it to `/prompt` or
comparing it with `scripts/graph_diff.py`, which refuses a UI workflow (exit 3).

## Failure classes

- HTTP failure: network, firewall, VPN, or binding problem.
- `node_errors`: graph or installed-model mismatch; do not retry unchanged.
- `status_str: error`: runtime failure; report the failing node and concise cause.
- `status_str: success`: download and inspect every declared output. Depending
  on the save node, video can be reported under `images` with
  `animated: true`, not under a dedicated `video` key. A 3D save node reports
  under a `3d` key (`{"3d":[{"filename":"….glb","subfolder":"3d","type":"output"}]}`);
  the client downloads any entry that carries a `filename`.
