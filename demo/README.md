# Try Foxrun with a local model

This experimental Codespaces demo runs real Foxrun task commands with a small, self-hosted Gemma model. It requires no model API key and spends no paid model tokens. GitHub Codespaces compute and storage are still subject to your account's quotas and billing.

[Open the demo branch in Codespaces](https://codespaces.new/otmd-ai-agent/foxrun?ref=demo%2Fcodespaces-gemma)

Select a **4-core / 16 GB RAM** machine with at least **32 GB storage**. This configuration targets Linux x86-64. The first startup builds the development container and downloads a **5.15 GB** model. Open the private forwarded **port 8080** when Codespaces offers it; the page shows setup progress.

## Try it

1. Click **Use a sample task**, then **Send to local Gemma**.
2. Note the task ID. Ask: “Read task T2, write three useful checklist items about creating a task, reading its proof, and accepting it after review, then submit the checklist as proof,” replacing T2 with your ID.
3. Expand **Read saved proof**. Check the result against the acceptance criteria, check the review box, and click **Accept as visitor**.
4. Click **New chat · keep tasks**. Ask: “What tasks did I work on? Read the saved records.”
5. Expand **What the agent actually did** to see the real tool results.

Foxrun creates a starter housekeeping task named “Session work to place.” It is normal to see that before creating your own task.

Use synthetic information only. Tasks, proof, and local runtime logs can remain in the codespace. The app's chat history is in process memory; **New chat** clears that history, not the task database. Container replacement/rebuild discards the demo install under `/tmp/foxrun-demo`. The model cache uses a Docker volume and may survive a container rebuild. Delete the codespace and its storage to discard everything. There is no external backup or export service.

## What is real, and what is limited

The UI reads Foxrun's SQLite records. Task creation, claiming, proof submission, and acceptance go through `work/work.py`; the adapter never writes task rows directly. Foxrun enforces its evidence and independent-review rules. The model can list tasks, create tasks, and submit Markdown proof. Only the separate human UI can accept a result.

The adapter is a small OpenAI-compatible tool loop, not Claude Code or Codex. It does not run the full seven-seat team, autonomous workflows, nightly memory, capture, or business integrations. It has no arbitrary shell or external-action tool. The displayed CLI outputs are proof that an action occurred; model narration is not. If Gemma returns an empty follow-up, the UI labels the actual result **Foxrun tool results** rather than inventing an AI answer.

The model is small and can make poor decisions, misunderstand acceptance criteria, or return malformed tool calls. Review what happened before retrying after an error. Keep the Codespaces forwarded port **private**; this is a single-visitor demo, not a multi-user service.

## Model choice

The suggested `google/gemma-4-E4B-it-qat-mobile-ct` checkpoint uses mobile-oriented compressed tensors. This CPU demo instead uses Google's official **Gemma 4 E4B instruction-tuned QAT Q4_0 GGUF** through Docker Model Runner's llama.cpp backend. These are different checkpoint formats. The mobile-ct checkpoint was inspected but not executed in this test; the CPU runner image does not include vLLM.

- [Model repository](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf)
- Revision: `4b4a2c1d584be7264f87aac328a1bc739ce81b6c`
- File: `gemma-4-E4B_q4_0-it.gguf` (5,154,941,280 bytes)
- SHA-256: `676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee`
- [Model card and license](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf/blob/4b4a2c1d584be7264f87aac328a1bc739ce81b6c/README.md)
- Text-only: the separate image/audio projector is not downloaded.
- Context: 4,096 tokens; four CPU threads; no GPU requested.
- DMR image: `docker/model-runner@sha256:60e6a14d8cc331fab3e51d7b78bba98274b4d28573f4e0b345e475d52d167869`
- Packaging CLI: official `dmr-v0.1.0` Linux amd64 binary; its archive checksum is verified in the Dockerfile.

The download is revision-pinned and checked against Hugging Face's LFS SHA-256 before packaging. The HTTP CDN ETag is not used as the file checksum. No model weights or personal data are committed to Git.

## Development and checks

The devcontainer consists of a Python development service and a Docker Model Runner sidecar. Only the UI port is forwarded. `postStartCommand` runs `demo/start.py`, which starts the page immediately and performs installation/model preparation in the background. Reopening a running demo does not start another server.

```sh
# In the devcontainer, if the page needs starting:
python3 demo/start.py

# Tests install isolated temporary Foxrun systems; no model is needed:
python3 -m unittest discover -s demo -p 'test_*.py' -v

# Check the Compose definition:
docker compose -f .devcontainer/compose.yaml config --quiet
```

Setup logs are `/tmp/foxrun-demo/prepare.log`, `install.log`, `doctor.log`, and `model-load.log`. If setup fails, read the named log. A failed initial install can leave partial files; rebuild the demo container to start with empty disposable folders. The page does not silently substitute a hosted model.

`MODEL_RUNNER_HOST` selects the sidecar, and `FOXRUN_DEMO_ROOT` selects isolated demo storage. For controlled tests only, `DMR_BIN` can name an existing CLI and `FOXRUN_DEMO_MODEL_FILE` can reuse a downloaded GGUF; its checksum is still verified. The normal Codespaces path needs none of those overrides.

## Verification and limits

Tested on 4 November 2026 in a Linux x86-64 cloud environment with 5 available CPUs and about 17.6 GiB RAM, using four model threads:

- Docker image built and the app ran as non-root with the source mounted read-only.
- Fresh Linux installation passed Foxrun doctor.
- Local Gemma made a real task-creation call: approximately **26 seconds cold**, **8.4 seconds warm** in the sampled runs. These are observations, not performance guarantees.
- The model download took about **4 minutes 27 seconds** over this environment's connection.
- The loaded llama-server process had approximately **7.4 GiB RSS**. Docker's container-wide memory statistics were not reliable in this rootless test environment.
- Integration tests cover creation → proof → review → acceptance, rejection of self-acceptance, invalid tool/path rejection, and retrieval of saved records.
- A real browser completed proof submission, human acceptance, and a new-chat lookup at a 390-pixel viewport without horizontal overflow.
- An initial model result contained placeholder checklist items. A stronger prompt read the task first and submitted proof in **29.6 seconds**. Empty follow-up responses still occurred; the UI explicitly displays verified tool output instead. This is a mechanics demo, not evidence of production agent quality.

The Codespaces machine API returned **403 Resource not accessible by integration**, so no actual GitHub Codespace was provisioned from this session. Docker execution is verified here; the first Codespaces launch remains a separate acceptance check.
