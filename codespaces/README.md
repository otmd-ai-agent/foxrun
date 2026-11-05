# Foxrun in Codespaces with OpenCode

This setup runs the OpenCode browser application on private port **8081**, with a local Gemma model served by Docker Model Runner. OpenCode uses Foxrun's installer, onboarding skills, agent seats, work commands, and memory integration.

This is intended for a disposable session of about an hour. The configuration skips nightly scheduling and backup prompts. Delete the Codespace and its storage when you finish.

## Start

1. Create a Codespace from the branch containing this configuration. Use a Linux x86-64 machine with at least 4 CPUs, 16 GB RAM, and 32 GB storage.
2. Wait for the container image. Its first build downloads and verifies the **5.15 GB** model. A ready Codespaces prebuild reuses that image. Startup imports the cached file into Docker Model Runner before OpenCode opens; it does not download weights from Hugging Face.
3. The editor is configured to detect port **8081** and open it in a separate browser tab. If the tab does not open, choose **Ports → 8081 → Open in Browser**. Keep the port private and its protocol HTTP; GitHub supplies the browser's HTTPS address.
4. Sign in to OpenCode with username `opencode`. Show your generated password in the Codespaces terminal:

   ```sh
   python3 codespaces/start.py --password
   ```

5. Open the `/workspaces/foxrun-state/launch` project in OpenCode and run `/foxrun-setup`. The skill asks for your name and first workspace, then offers the actual Foxrun setup steps. It installs from this checkout with `--runtime opencode`.
6. Continue in the workspace you created under `/workspaces/foxrun-state/portfolio/`. Foxrun's agent threads and skills operate on the installed files and task database there.

OpenCode runs commands and edits files with the Codespace user's permissions. Its normal approval controls remain available. Both its main and small-model settings use the local Docker Model Runner provider; hosted providers are not enabled by this configuration.

## Storage and configuration

The container account's home is `/workspaces/foxrun-state/user`. Startup creates checked `~/.foxrun` and `~/foxrun` aliases to the installed system and portfolio, so existing product skills that use those default paths reach the same records. Startup refuses conflicting paths and never changes the caller's home environment. A rebuild is required to adopt this account-home setting.

The `foxrun-state` Docker volume holds the installed system, portfolio, OpenCode sessions, transcripts, configuration, and generated browser password. The image keeps the verified GGUF at `/opt/foxrun-model/model.gguf`, outside both volumes. The separate `model-cache` volume holds Model Runner's imported copy. A new or empty model volume can be populated from the image without downloading the weights again. Restarting the app keeps these records. Deleting the Codespace and its associated storage discards them; this setup creates no external backup.

The startup script does not invent a person or workspace and does not install Foxrun before onboarding. It copies the three bootstrap skills into the launch project. The real installer creates the complete skill shelf after you supply your details. The browser interface belongs to OpenCode.

The model is Google's Gemma 4 E4B instruction-tuned QAT Q4_0 GGUF, pinned to revision `4b4a2c1d584be7264f87aac328a1bc739ce81b6c`, with SHA-256 `676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee`. This configuration uses a **32,768-token** context and four CPU threads. The model's published context limit is 128K, but this configuration reserves a smaller window for the agent. Actual memory use at this setting has not been measured; the 16 GB machine target still needs validation. CPU inference can be slow, and a small model can make mistakes even when the integration works. Review the actual tool results.

OpenCode is pinned to **1.19.5**. Its official Linux x64 archive is verified against SHA-256 `588310a336fa3b9df36b3f0225b26f679d453efaad0cf3d66c3651ef3ec1647a`. Docker Model Runner and its packaging CLI remain pinned in the Dockerfile and Compose file.

## Enable prebuilds

An administrator must enable prebuilds in [the repository's Codespaces settings](https://github.com/otmd-ai-agent/foxrun/settings/codespaces). Updating the devcontainer files does not turn this setting on.

1. Choose **Set up prebuild** and select `codex/codespaces-opencode` with `.devcontainer/devcontainer.json`.
2. Use **Every push** while testing this branch so changes to the model downloader also refresh the image. Select the region where you create Codespaces and retain one version if you only need the latest build.
3. Wait for **Prebuild ready**, then create a new Codespace from this branch. Enabling prebuilds does not accelerate a Codespace already being created.

The first prebuild still downloads the model. Later Codespaces must transfer the prepared image and import the model locally, so startup is not instantaneous. The model bytes stay out of Git; only their URL, checksum, and preparation code are committed. Prebuilds consume GitHub Actions time and storage.

The cache is a Docker image layer, not a named-volume snapshot. This avoids relying on GitHub to preserve the Model Runner volume. Actual image build and restoration from a GitHub prebuild still need a live check. Confirm the setup page says **Prebuilt codespace found**, then confirm startup reports **Importing the model from the image cache** rather than a model download.

See [GitHub's prebuild configuration guide](https://docs.github.com/en/codespaces/prebuilding-your-codespaces/configuring-prebuilds) and [prebuild troubleshooting](https://docs.github.com/en/codespaces/troubleshooting/troubleshooting-prebuilds).

## Checks and troubleshooting

Run these commands from the source checkout:

```sh
python3 codespaces/start.py
python3 -m unittest discover -s codespaces -p 'test_*.py' -v
python3 codespaces/check_integration.py --opencode /usr/local/bin/opencode
tail -n 60 /workspaces/foxrun-state/opencode.log
tail -n 60 /workspaces/foxrun-state/model-load.log
```

Startup checks OpenCode's authenticated health endpoint and refuses to replace an unrelated process on port 8081. Running startup again reuses the existing healthy server.

If the browser returns HTTP 502 while OpenCode is healthy, remove the existing port forwarding entry, add port 8081 again, select **Change Port Protocol → HTTP**, and use **Open in Browser**. That recovered the previous demo in a live Codespace. Automatic forwarding and browser launch for this OpenCode configuration still require a fresh Codespace test.

Thirteen local tests cover image-cache reuse, interrupted and invalid downloads, fresh-volume imports without weight downloads, configuration preservation, checked home aliases, private credentials, repeat startup, and occupied-port handling. The pinned OpenCode binary passed config validation, served its authenticated health and skill endpoints, and loaded its real browser UI in Chromium with no failed requests or page errors. Docker execution is unavailable in the development session used for this change. The reproducible integration check runs the real installer and OpenCode lifecycle against a deterministic local HTTP model fixture in temporary storage. It also checks commands through the default-path aliases using an injected temporary home path; it does not change the test runner's home. It does not download or run Gemma. These checks do not establish end-to-end Gemma tool use or Codespaces browser behavior.

References: [OpenCode web interface](https://opencode.ai/docs/web/), [Docker Model Runner integration](https://docs.docker.com/guides/opencode-model-runner/), and [the pinned Gemma model card](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf/blob/4b4a2c1d584be7264f87aac328a1bc739ce81b6c/README.md).
