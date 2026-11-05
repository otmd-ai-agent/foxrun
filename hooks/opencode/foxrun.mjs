import { spawn } from "node:child_process";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// OpenCode retains its native sessions. This export lets Foxrun's settlement and
// handoff commands read the same messages without a second agent loop.
function transcriptRows(messages, childSession = false) {
  const rows = [];
  for (const { info, parts = [] } of messages) {
    const role = info.role;
    if (role !== "user" && role !== "assistant") continue;
    const timestamp = new Date(info.time?.created ?? Date.now()).toISOString();
    const content = [];
    const results = [];
    const generated = [];
    for (const part of parts) {
      if (part.type === "text") {
        const text = { type: "text", text: part.text };
        if (part.synthetic || part.ignored) generated.push({ ...text, synthetic: !!part.synthetic, ignored: !!part.ignored });
        else content.push(text);
      }
      if (part.type !== "tool") continue;
      const state = part.state ?? {};
      content.push({ type: "tool_use", id: part.callID, name: part.tool, input: state.input ?? {} });
      if (state.status === "completed" || state.status === "error") {
        results.push({ type: "tool_result", tool_use_id: part.callID,
          content: state.output ?? state.error ?? "", is_error: state.status === "error" });
      }
    }
    rows.push({ type: role, runtime: "opencode", sessionId: info.sessionID, timestamp,
      isMeta: role === "user" && childSession,
      message: { role, model: info.modelID, content } });
    if (generated.length) rows.push({ type: role, runtime: "opencode", sessionId: info.sessionID,
      timestamp, isMeta: true, message: { role, content: generated } });
    if (results.length) rows.push({ type: "user", runtime: "opencode", sessionId: info.sessionID,
      timestamp, isMeta: true, message: { role: "user", content: results } });
  }
  return rows;
}

export const FoxrunPlugin = async ({ client, directory }) => {
  const home = resolve(process.env.FOXRUN_HOME ?? join(dirname(fileURLToPath(import.meta.url)), "../.."));
  const configRoot = process.env.OPENCODE_CONFIG_DIR ??
    join(process.env.XDG_CONFIG_HOME ?? join(homedir(), ".config"), "opencode");
  const installedURI = pathToFileURL(join(home, "hooks/opencode/foxrun.mjs")).href;
  const enabled = async () => {
    try {
      const config = JSON.parse(await readFile(join(configRoot, "opencode.json"), "utf8"));
      return Array.isArray(config.plugin) && config.plugin.some(item =>
        item === installedURI || (Array.isArray(item) && item[0] === installedURI));
    } catch (error) {
      if (error.code === "ENOENT") return false;
      throw error;
    }
  };
  const transcriptRoot = resolve(process.env.FOXRUN_OPENCODE_TRANSCRIPTS ??
    join(process.env.XDG_STATE_HOME ?? join(homedir(), ".local/state"), "foxrun/opencode"));
  const sessions = new Map();
  const locks = new Map();

  const session = (id) => {
    if (!/^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/.test(id)) throw new Error("Invalid OpenCode session ID");
    if (!sessions.has(id)) sessions.set(id, { context: "", needsStart: true, afterCompact: false });
    return sessions.get(id);
  };
  const serialized = (id, action) => {
    const next = (locks.get(id) ?? Promise.resolve()).catch(() => {}).then(action);
    locks.set(id, next);
    return next.finally(() => { if (locks.get(id) === next) locks.delete(id); });
  };
  const metadata = async (id) => {
    const state = session(id);
    if (!state.metadataLoaded) {
      const response = await client.session.get({ path: { id }, query: { directory } });
      if (response.error || !response.data) throw new Error("Could not read OpenCode session metadata");
      state.parentID = response.data.parentID;
      state.metadataLoaded = true;
    }
    return state;
  };
  const exportTranscript = async (id) => {
    const state = await metadata(id);
    const response = await client.session.messages({ path: { id }, query: { directory } });
    if (response.error || !Array.isArray(response.data)) throw new Error("Could not read the OpenCode session for its Foxrun handoff");
    await mkdir(transcriptRoot, { recursive: true, mode: 0o700 });
    const destination = join(transcriptRoot, `${id}.jsonl`);
    const temporary = `${destination}.${process.pid}.tmp`;
    const rows = transcriptRows(response.data, !!state.parentID);
    await writeFile(temporary, rows.map(row => JSON.stringify(row)).join("\n") + "\n", { mode: 0o600 });
    await rename(temporary, destination);
    return destination;
  };
  const run = async (event, id, transcript) => {
    const state = await metadata(id);
    const payload = { runtime: "opencode", session_id: id, cwd: directory,
      transcript_path: transcript, model: state.model, agent_id: state.parentID ? id : undefined };
    return new Promise((accept, reject) => {
      const child = spawn("python3", ["-B", join(home, "hooks/opencode/bridge.py"), event],
        { env: { ...process.env, FOXRUN_HOME: home }, stdio: ["pipe", "pipe", "pipe"] });
      let stdout = "", stderr = "";
      const timer = setTimeout(() => child.kill("SIGTERM"), 120_000);
      child.stdout.on("data", chunk => { stdout += chunk; });
      child.stderr.on("data", chunk => { stderr += chunk; });
      child.on("error", error => { clearTimeout(timer); reject(error); });
      child.on("close", code => {
        clearTimeout(timer);
        if (code !== 0) return reject(new Error(stderr.trim() || `Foxrun hook exited ${code}`));
        try { accept(JSON.parse(stdout)); } catch { reject(new Error("Foxrun hook returned invalid JSON")); }
      });
      child.stdin.on("error", () => {});
      child.stdin.end(JSON.stringify(payload));
    });
  };
  const report = async (error) => {
    await client.app.log({ body: { service: "foxrun", level: "error", message: String(error) } });
  };
  return {
    "chat.message": async (input) => {
      const state = session(input.sessionID);
      state.model = input.model ? `${input.model.providerID}/${input.model.modelID}` : state.model;
      state.needsStart = true;
    },
    "experimental.chat.system.transform": async (input, output) => {
      if (!input.sessionID || !await enabled()) return;
      await serialized(input.sessionID, async () => {
        const state = session(input.sessionID);
        if (state.needsStart || state.afterCompact) {
          const result = await run(state.afterCompact ? "after-compact" : "start", input.sessionID);
          state.context = result.context;
          state.needsStart = !result.installed;
          state.afterCompact = false;
        }
        if (state.context) output.system.push(state.context);
      });
    },
    "experimental.session.compacting": async (input, output) => {
      if (!await enabled()) return;
      await serialized(input.sessionID, async () => {
        const transcript = await exportTranscript(input.sessionID);
        const result = await run("before-compact", input.sessionID, transcript);
        if (result.context) output.context.push(result.context);
        session(input.sessionID).afterCompact = true;
      });
    },
    "shell.env": async (input, output) => {
      output.env.FOXRUN_HOME = home;
      if (process.env.FOXRUN_PORTFOLIO) output.env.FOXRUN_PORTFOLIO = process.env.FOXRUN_PORTFOLIO;
      if (input.sessionID) output.env.FOXRUN_SESSION_ID = input.sessionID;
    },
    event: async ({ event }) => {
      if (!await enabled()) return;
      const id = event.properties?.sessionID ?? event.properties?.info?.id;
      if (!id) return;
      if (event.properties?.info) {
        session(id).parentID = event.properties.info.parentID;
        session(id).metadataLoaded = true;
      }
      if (event.type === "session.compacted") session(id).afterCompact = true;
      if (event.type !== "session.idle" && event.type !== "session.deleted") return;
      await serialized(id, async () => {
        try {
          if (event.type === "session.idle") {
            const transcript = await exportTranscript(id);
            await run("idle", id, transcript);
            session(id).needsStart = true;
          } else {
            await run("end", id);
            sessions.delete(id);
          }
        } catch (error) { await report(error); }
      });
    },
  };
};
