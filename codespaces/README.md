# Foxrun in Codespaces with OpenCode

This setup runs the OpenCode browser application on private port **8081**, with a local Gemma model served by Docker Model Runner. OpenCode uses Foxrun's installer, onboarding skills, agent seats, work commands, and memory integration.

This is intended for a disposable session of about an hour. The configuration skips nightly scheduling and backup prompts. Delete the Codespace and its storage when you finish.

## Start

1. Create a Codespace from the branch containing this configuration. Use a Linux x86-64 machine with at least 4 CPUs, 16 GB RAM, and 32 GB storage.
2. Wait for the container build and model download. First startup downloads a verified **5.15 GB** model; progress appears in the container startup output. OpenCode starts after model packaging succeeds.
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

The `foxrun-state` Docker volume holds the installed system, portfolio, OpenCode sessions, transcripts, configuration, and generated browser password. The separate `model-cache` volume holds the model. Restarting the app keeps these records. Deleting the Codespace and its associated storage discards them; this setup creates no external backup.

The startup script does not invent a person or workspace and does not install Foxrun before onboarding. It copies the three bootstrap skills into the launch project. The real installer creates the complete skill shelf after you supply your details. The browser interface belongs to OpenCode.

The model is Google's Gemma 4 E4B instruction-tuned QAT Q4_0 GGUF, pinned to revision `4b4a2c1d584be7264f87aac328a1bc739ce81b6c`, with SHA-256 `676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee`. This configuration uses a **32,768-token** context and four CPU threads. The model's published context limit is 128K, but this configuration reserves a smaller window for the agent. Actual memory use at this setting has not been measured; the 16 GB machine target still needs validation. CPU inference can be slow, and a small model can make mistakes even when the integration works. Review the actual tool results.

OpenCode is pinned to **1.19.5**. Its official Linux x64 archive is verified against SHA-256 `588310a336fa3b9df36b3f0225b26f679d453efaad0cf3d66c3651ef3ec1647a`. Docker Model Runner and its packaging CLI remain pinned in the Dockerfile and Compose file.

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

Seven local tests cover configuration preservation, checked home aliases, private credentials, repeat startup, occupied-port handling, and rejection of a model with the wrong checksum. The pinned OpenCode binary passed config validation, served its authenticated health and skill endpoints, and loaded its real browser UI in Chromium with no failed requests or page errors. Docker execution is unavailable in the development session used for this change. The reproducible integration check runs the real installer and OpenCode lifecycle against a deterministic local HTTP model fixture in temporary storage. It also checks commands through the default-path aliases using an injected temporary home path; it does not change the test runner's home. It does not download or run Gemma. These checks do not establish end-to-end Gemma tool use or Codespaces browser behavior.

References: [OpenCode web interface](https://opencode.ai/docs/web/), [Docker Model Runner integration](https://docs.docker.com/guides/opencode-model-runner/), and [the pinned Gemma model card](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf/blob/4b4a2c1d584be7264f87aac328a1bc739ce81b6c/README.md).
