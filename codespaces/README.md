# Foxrun in Codespaces with OpenCode

This setup runs the OpenCode browser application on private port **8081**, with a local Gemma model served by Docker Model Runner. OpenCode uses Foxrun's installer, onboarding skills, agent seats, work commands, and memory integration.

This is intended for a disposable session of about an hour. The configuration skips nightly scheduling and backup prompts. Delete the Codespace and its storage when you finish.

## Start

1. Create a Codespace from the branch containing this configuration. Use a Linux x86-64 machine with at least 4 CPUs, 16 GB RAM, and 32 GB storage.
2. Wait for the container image, then follow startup in `/workspaces/foxrun-state/startup.log`. On a cold start, Docker Model Runner pulls the pinned **4.09 GB Gemma 4 E2B** artifact directly into its model volume. Startup configures CPU inference and requires an exact `READY` answer before opening OpenCode. Later starts reuse the cached model.
3. The editor is configured to detect port **8081** and open it in a separate browser tab. If the tab does not open, choose **Ports → 8081 → Open in Browser**. Keep the port private and its protocol HTTP; GitHub supplies the browser's HTTPS address.
4. Sign in to OpenCode with username `opencode`. Show your generated password in the Codespaces terminal:

   ```sh
   python3 codespaces/start.py --password
   ```

5. Open the `/workspaces/foxrun-state/launch` project in OpenCode and run `/foxrun-setup`. The skill asks for your name and first workspace, then offers the actual Foxrun setup steps. It installs from this checkout with `--runtime opencode`.
6. Continue in the workspace you created under `/workspaces/foxrun-state/portfolio/`. Foxrun's agent threads and skills operate on the installed files and task database there.

OpenCode runs commands and edits files with the Codespace user's permissions. Its normal approval controls remain available. Both its main and small-model settings use the local Docker Model Runner provider; hosted providers are not enabled by this configuration.

## Storage and configuration

The configuration requests four CPUs, 16 GB RAM, and 32 GB storage, matching the available Codespaces machine. Model Runner stores the roughly 4.09 GB model in its own volume. There is no separate GGUF in the application image and no packaging/import copy. Container images, tools, and user files still need disk space; available capacity alone does not guarantee that a download will fit. Pull failures are recorded in `startup.log`.

The container account's home is `/workspaces/foxrun-state/user`. Startup creates checked `~/.foxrun` and `~/foxrun` aliases to the installed system and portfolio, so existing product skills that use those default paths reach the same records. Startup refuses conflicting paths and never changes the caller's home environment. A rebuild is required to adopt this account-home setting.

The `foxrun-state` Docker volume holds the installed system, portfolio, OpenCode sessions, transcripts, configuration, and generated browser password. The separate `model-cache` volume holds Model Runner's model data. Restarting the app reuses these volumes; a new or empty model volume requires a download. Deleting the Codespace and its associated storage discards them; this setup creates no external backup.

The startup script does not invent a person or workspace and does not install Foxrun before onboarding. It copies the three bootstrap skills into the launch project. The real installer creates the complete skill shelf after you supply your details. The browser interface belongs to OpenCode.

The model and pull/configuration/probe sequence come from the [working semantic-contracts workshop](https://github.com/onthemarkdata/semantic-contracts-workshop/blob/7cece7c44725a23da05349c64f198d9e810109b1/docs/model-runner.md). `gemma.lock.json` pins Docker's Gemma 4 E2B Q4_K_M artifact by manifest digest. This is Docker's distribution of an Unsloth conversion of Google's model. Model Runner verifies the registry artifact; the client resolves the exact digest again after a pull and rejects streamed pull errors.

Foxrun retains a **32,768-token** context for OpenCode's tools, skills, and conversation, while the workshop's short checks use 4,096 tokens. Both use four CPU threads, one inference slot, Jinja templates, and disabled thinking. The workshop's successful text checks do not validate Foxrun's larger context or tool use. Memory use and full onboarding still need a live 16 GB Codespace check. CPU inference can be slow; review actual tool results.

OpenCode is pinned to **1.19.5**. Its official Linux x64 archive is verified against SHA-256 `588310a336fa3b9df36b3f0225b26f679d453efaad0cf3d66c3651ef3ec1647a`. Docker Model Runner remains pinned by digest in the Compose file; startup uses its HTTP API and needs no packaging CLI.

## Prebuilds and model caching

A Codespaces prebuild can prepare the OpenCode application image and its tools. This configuration pulls the model directly into Model Runner's volume on the first start; it does not bake weights into the application image. Do not assume GitHub prebuilds preserve that named volume. A new Codespace may still need the 4.09 GB download; restarts with the existing model volume reuse it.

An administrator can enable prebuilds in [the repository's Codespaces settings](https://github.com/otmd-ai-agent/foxrun/settings/codespaces), selecting `codex/codespaces-opencode` and `.devcontainer/devcontainer.json`. Wait for **Prebuild ready** before creating a Codespace. Prebuilds consume GitHub Actions time and storage. See [GitHub's configuration guide](https://docs.github.com/en/codespaces/prebuilding-your-codespaces/configuring-prebuilds).

## Checks and troubleshooting

If an older revision entered recovery mode with `Model setup needs at least 11.4 GB free`, both services may already have started: the model startup check failed afterward. Update this branch with `git pull --ff-only`. On [your Codespaces page](https://github.com/codespaces), check storage capacity and usage. If space is still low, remove only files you no longer need, or choose a larger machine through **… → Change machine type** if your account offers one. Then rebuild the container. The available machine types depend on the account and organization policy; this repository's agent account currently offers only 32 GB machines. Rebuilding alone does not increase capacity. See [GitHub's machine-type guide](https://docs.github.com/en/codespaces/customizing-your-codespace/changing-the-machine-type-for-your-codespace?tool=webui). A larger machine may have a higher billing rate.

If the editor's creation-log command is unavailable, read the log in the recovery terminal:

```sh
tail -n 80 /workspaces/.codespaces/.persistedshare/creation.log
```

Run these commands from the source checkout:

```sh
python3 codespaces/start.py
python3 -m unittest discover -s codespaces -p 'test_*.py' -v
python3 codespaces/check_integration.py --opencode /usr/local/bin/opencode
tail -n 60 /workspaces/foxrun-state/startup.log
tail -n 60 /workspaces/foxrun-state/opencode.log
```

The container launches startup in the background. A model or app startup failure is written to `startup.log` and does not fail the container lifecycle command. After fixing the reported issue, run `python3 codespaces/start.py` to retry in the foreground.

Startup checks OpenCode's authenticated health endpoint and refuses to replace an unrelated process on port 8081. Running startup again reuses the existing healthy server.

If the browser returns HTTP 502 while OpenCode is healthy, remove the existing port forwarding entry, add port 8081 again, select **Change Port Protocol → HTTP**, and use **Open in Browser**. That recovered the previous demo in a live Codespace. Automatic forwarding and browser launch for this OpenCode configuration still require a fresh Codespace test.

Local tests cover streamed pull failures, incomplete downloads, cached-model inference failures, incorrect probe answers, configuration preservation, checked home aliases, private credentials, background startup errors, repeat startup, and occupied ports. An HTTP fixture exercises cold and warm initialization with the exact model digest and configured context. These fixtures do not download or run Gemma.

The reproducible integration check runs the real installer and pinned OpenCode host against a deterministic local model fixture. It checks installed skills, lifecycle hooks, transcripts, handoffs, compaction, and commands through default-path aliases using a temporary home. It does not change the test runner's home. Docker execution is unavailable in the development session used for this change. Full Gemma tool use and Codespaces browser behavior remain live validation gates.

References: [OpenCode web interface](https://opencode.ai/docs/web/), [Docker Model Runner integration](https://docs.docker.com/guides/opencode-model-runner/), and [the workshop model lock](https://github.com/onthemarkdata/semantic-contracts-workshop/blob/7cece7c44725a23da05349c64f198d9e810109b1/models/gemma.lock.json).
