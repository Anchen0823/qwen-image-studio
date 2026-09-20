---
name: qwen-image-local
description: Generate or edit images with the locally installed Qwen-Image-2.1 model on Windows. Use when the user requests local Qwen image generation, reference-image editing, or batches through the Qwen desktop workbench queue.
---

# Local Qwen Image

Use the shared desktop queue through `scripts/qwen.py`. It delegates to the workbench CLI, prints JSON, and does not require opening the UI. The local default workbench is `D:\users\self_projects\qwen_`; override with `QWEN_WORKBENCH` if relocated. The default model is `D:\AI\Qwen-Image-2.1`; override with `QWEN_MODEL_DIR`.

Run the helper with the model Python environment, normally `D:\AI\Qwen-Image-2.1\.venv\Scripts\python.exe`. Quote paths and pass arguments separately; use UTF-8 files for multiline prompts so shell quoting cannot alter them.

## Workflow

1. Prepare a UTF-8 JSON array of tasks. Each task accepts `prompt`, `width`, `height`, `steps`, `seed`, and optional `edit` (absolute reference-image path). Defaults: 512×512, 40 steps, seed -1. Preserve the user's actual prompt and settings. Dimensions are multiples of 16, 256–1536; steps are 1–100. Use 512×512 initially on the local 8GB GPU unless the user requests otherwise.
2. Call `scripts/qwen.py submit --batch <absolute-json-path>`. Record returned task IDs. Submission means queued, not generated. The same queue is visible in the desktop. A paused queue stays paused; report that state rather than silently resuming unrelated queued work.
3. If the desktop is running, it automatically executes queued tasks. Otherwise call `scripts/qwen.py run` to drain the queue. It may run for several minutes; use the host's yielded execution session for long calls. Multiple runners share an OS lock and cannot normally run GPU jobs concurrently. `runner_acquired: false` means another runner is active, not a generation failure.
4. Inspect `scripts/qwen.py status --id <id>`, or use `wait <id> [<id>...] --timeout 60`. `wait` never starts a runner. Only `status: completed` with an existing readable PNG is success. Read the returned `spec.output`; metadata and logs use the same stem with `.json` and `.log`.
5. Visually inspect the output and show the local image to the user. Distinguish successful execution from image quality. Low-step smoke tests do not establish normal rendering quality. Failures remain recorded, and the queue continues with the next task. Report the specific `error` and inspect the log before considering a retry; do not loop retries indefinitely.

`cancel <id>` cancels only that queued/running task. `retry <id>` requeues failed, cancelled, or interrupted tasks with the same seed. `pause` stops dispatch after the current task finishes; `resume` permits dispatch but does not itself start a runner. Change queue-wide state only when it matches the user's request. Closing the GUI interrupts its active task; pending tasks remain saved. Interrupted tasks require explicit retry.

Example batch:

```json
[
  {"prompt": "雨后江南街巷，暖色灯光，电影摄影", "width": 512, "height": 512, "steps": 40, "seed": -1},
  {"prompt": "给参考图中的猫戴上一顶蓝帽子", "edit": "D:/images/cat.png", "steps": 40, "seed": 42}
]
```

No remote inference service, model download, or model-file modification is needed. Generated images stay in the workbench `outputs` directory. Do not include model weights, private prompts, queue databases, or generated images in source-control publication unless separately requested.
