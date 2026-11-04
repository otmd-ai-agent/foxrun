# Try Foxrun with a local model

Try Foxrun before installing it on your machine: ask a small, self-hosted Gemma model to create a task and submit proof, review the result yourself, then find the saved record in a new chat. The demo runs real Foxrun task commands. You need no model API key and spend no paid model tokens; GitHub Codespaces compute and storage still count toward your account's quotas and billing.

This is experimental. The demo has loaded in a browser from a GitHub Codespace, but the embedded editor preview and the complete task workflow in Codespaces remain unverified.

## Open the demo

[Open the demo branch in Codespaces](https://codespaces.new/otmd-ai-agent/foxrun?ref=codex%2Fcodespaces-editor-preview)

1. Select a **4-core / 16 GB RAM** machine with at least **32 GB storage**. The configuration targets Linux x86-64.
2. Allow the first startup to build the development container and download the **5.15 GB** model.
3. Codespaces is configured to open forwarded **port 8081** with **Preview in Editor**. If it does not open, select that action on port 8081 in the **Ports** panel. The page shows setup progress. Keep the port **private**: the demo supports one visitor.

Use synthetic information only. The demo stores tasks and proof in the codespace until you discard that storage; closing a chat does not erase them.

## Try it

1. Click **Use a sample task**, then **Send to local Gemma**.
2. Note the task ID. Ask: “Read task T2, write three useful checklist items about creating a task, reading its proof, and accepting it after review, then submit the checklist as proof,” replacing T2 with your ID.
3. Expand **Read saved proof**. Check the result against the acceptance criteria, check the review box, and click **Accept as visitor**.
4. Click **New chat · keep tasks**. Ask: “What tasks did I work on? Read the saved records.”
5. Expand **What the agent actually did** to see the real tool results.

You may already see a task named “Session work to place.” Foxrun creates this housekeeping task during setup.

## When you finish

Delete the codespace and its storage to discard everything. Tasks, proof, and local runtime logs can remain there between visits. There is no external backup or export service.

The reset options affect different data:

- **New chat** clears the chat history held in process memory. The task database stays available.
- Replacing or rebuilding the container discards the demo install under `/tmp/foxrun-demo`.
- The model cache lives in a Docker volume and may survive a container rebuild.

## How the demo uses Foxrun

The model can list tasks, create tasks, and submit Markdown proof. You accept a result through a separate human UI. Task creation, claiming, proof submission, and acceptance all go through `work/work.py`, so Foxrun enforces its evidence and independent-review rules. The UI reads Foxrun's SQLite records; the adapter never writes task rows directly.

Gemma can misunderstand acceptance criteria, make poor decisions, or return malformed tool calls. Use the displayed CLI output to check whether an action occurred, and review it before retrying after an error. Model narration alone does not verify an action. If Gemma returns an empty follow-up, the UI shows the actual output under **Foxrun tool results** without inventing an AI answer.

The adapter runs a small OpenAI-compatible tool loop. It uses neither Claude Code nor Codex and has no arbitrary shell or external-action tool. The full seven-seat team, autonomous workflows, nightly memory, capture, and business integrations are outside this demo's scope.

## Model choice

The demo runs Google's official **Gemma 4 E4B instruction-tuned QAT Q4_0 GGUF** through Docker Model Runner's CPU llama.cpp backend. The suggested `google/gemma-4-E4B-it-qat-mobile-ct` checkpoint uses a different format: mobile-oriented compressed tensors. That checkpoint was inspected but never executed in this test. The CPU runner image does not include vLLM.

- [Model repository](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf)
- Revision: `4b4a2c1d584be7264f87aac328a1bc739ce81b6c`
- File: `gemma-4-E4B_q4_0-it.gguf` (5,154,941,280 bytes)
- SHA-256: `676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee`
- [Model card and license](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf/blob/4b4a2c1d584be7264f87aac328a1bc739ce81b6c/README.md)
- Text-only: the separate image/audio projector is not downloaded.
- Context: 4,096 tokens; four CPU threads; no GPU requested.
- DMR image: `docker/model-runner@sha256:60e6a14d8cc331fab3e51d7b78bba98274b4d28573f4e0b345e475d52d167869`
- Packaging CLI: official `dmr-v0.1.0` Linux amd64 binary; its archive checksum is verified in the Dockerfile.

Before packaging, setup verifies the download from the pinned revision against Hugging Face's LFS SHA-256. It does not use the HTTP CDN ETag as the file checksum. No model weights or personal data are committed to Git.

## Development and checks

The devcontainer runs two services: a Python development service and a Docker Model Runner sidecar. Only the UI port is forwarded. At startup, `postStartCommand` runs `demo/start.py`. This serves the page immediately while installation and model preparation continue in the background. Reopening a running demo does not start another server. Chat submissions return immediately with a request ID; the page polls for the result while Gemma runs. Reloading the page recovers the current request while the server stays running. Recent request IDs prevent duplicate submissions within that server process. Restarting the server clears chat requests and history, but keeps saved task records.

```sh
# In the devcontainer, if the page needs starting:
python3 demo/start.py

# Tests install isolated temporary Foxrun systems; no model is needed:
python3 -m unittest discover -s demo -p 'test_*.py' -v

# Check the Compose definition:
docker compose -f .devcontainer/compose.yaml config --quiet
```

If setup fails, read the log named on the page. Setup logs are `/tmp/foxrun-demo/prepare.log`, `install.log`, `doctor.log`, and `model-load.log`. A failed initial install can leave partial files; rebuild the demo container to start with empty disposable folders. The page does not silently substitute a hosted model.

The server defaults to port 8081, matching the forwarded preview port in `.devcontainer/devcontainer.json`. `PORT` overrides the listener for development; forward the same port when using an override. Changes to the devcontainer configuration apply to a new or rebuilt container, so pulling a change does not replace an existing preview tab or forwarding entry.

If the page loads in a regular browser tab but the editor preview reports “github.com refused to connect,” the port is reachable but the embedded GitHub authentication flow may be blocked. The preview frame policy cannot change GitHub’s authentication policy. This remains a live Codespaces limitation under investigation.

Normal Codespaces setup needs no environment overrides. For development, `MODEL_RUNNER_HOST` selects the sidecar and `FOXRUN_DEMO_ROOT` selects isolated demo storage. For controlled tests only, `DMR_BIN` can name an existing CLI and `FOXRUN_DEMO_MODEL_FILE` can reuse a downloaded GGUF. Setup still verifies that file's checksum.

## Verification and limits

Docker and browser checks ran on 4 November 2026 in a Linux x86-64 cloud environment with 5 available CPUs and about 17.6 GiB RAM. The model used four CPU threads.

- Docker image built and the app ran as non-root with the source mounted read-only.
- Fresh Linux installation passed Foxrun doctor.
- Integration tests cover creation → proof → review → acceptance, rejection of self-acceptance, invalid tool/path rejection, and retrieval of saved records.
- A real browser completed proof submission, human acceptance, and a new-chat lookup at a 390-pixel viewport without horizontal overflow.

Local Gemma made a real task-creation call in approximately **26 seconds cold** and **8.4 seconds warm** in the sampled runs. An initial result contained placeholder checklist items. A stronger prompt read the task first and submitted proof in **29.6 seconds**, though empty follow-up responses still occurred. The UI displays verified tool output in those cases. These results show the task mechanics working; they do not establish production agent quality or guarantee response times.

The **5.15 GB** model download took about **4 minutes 27 seconds** over this environment's connection. The loaded llama-server process used approximately **7.4 GiB RSS**. Docker's container-wide memory statistics were unreliable in this rootless test environment.

The Codespaces machine API returned **403 Resource not accessible by integration**, preventing automated live validation in this session. User-provided checks confirmed that the queried page and health endpoint returned HTTP 200 in Codespaces, and the page loaded in a regular browser tab. A later live chat attempt showed an empty JSON response and lost state connection; the original logs were unavailable after the Codespace was reset. A controlled slow-model test reproduced a dropped long-running HTTP response. The updated server acknowledges chat requests immediately, and Chromium checks cover lost acknowledgements, page reloads, empty and non-JSON responses, and model errors without resubmitting the request. These tests use a mocked model. The embedded editor preview and complete task workflow still need live verification.
