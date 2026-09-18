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

## Saved workflows

List server-side workflows with:

```text
GET /api/userdata?dir=workflows&recurse=true
```

For `/userdata/{file}`, encode a nested path as one parameter, for example
`workflows%2Fexample.json`. A saved UI workflow is not automatically an API graph;
expand subgraphs or export it in API format before submitting it to `/prompt`.

## Failure classes

- HTTP failure: network, firewall, VPN, or binding problem.
- `node_errors`: graph or installed-model mismatch; do not retry unchanged.
- `status_str: error`: runtime failure; report the failing node and concise cause.
- `status_str: success`: download and inspect every declared output. Depending
  on the save node, video can be reported under `images` with
  `animated: true`, not under a dedicated `video` key.
