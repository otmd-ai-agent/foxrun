import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { test } from "node:test";
import { FoxrunPlugin } from "../hooks/opencode/foxrun.mjs";

test("native plugin preserves session context, tools, consent, and compaction boundaries", async () => {
  const root = await mkdtemp(join(tmpdir(), "foxrun-plugin-"));
  const home = join(root, "home");
  const config = join(root, "config");
  const transcripts = join(root, "transcripts");
  const saved = { ...process.env };
  let hooks;
  try {
    Object.assign(process.env, { FOXRUN_HOME: home, OPENCODE_CONFIG_DIR: config,
      FOXRUN_OPENCODE_TRANSCRIPTS: transcripts });
    await mkdir(join(home, "hooks/opencode"), { recursive: true });
    await mkdir(config);
    await writeFile(join(home, "hooks/opencode/bridge.py"), `import json, pathlib, sys
payload=json.load(sys.stdin)
with (pathlib.Path(__file__).parents[2]/'calls.jsonl').open('a') as f:
 f.write(json.dumps({'event':sys.argv[1],**payload})+'\\n')
print(json.dumps({'installed':True,'context':sys.argv[1]+':'+payload['session_id']}))
`);
    const messages = [{ info: { role: "user", sessionID: "ses_one", time: { created: 1000 } },
      parts: [{ type: "text", text: "Please save this decision." }] },
    { info: { role: "assistant", sessionID: "ses_one", modelID: "local-model", time: { created: 2000 } },
      parts: [{ type: "tool", tool: "bash", callID: "call_1", state: { status: "completed",
        input: { command: "python3 work.py create --title Example" }, output: "T42" } }] }];
    const errors = [];
    const client = { session: { messages: async () => ({ data: messages }),
      get: async ({ path }) => ({ data: { id: path.id, parentID: path.id === "ses_child" ? "ses_one" : undefined } }) },
      app: { log: async ({ body }) => { errors.push(body.message); } } };
    hooks = await FoxrunPlugin({ client, directory: root });
    await writeFile(join(config, "opencode.json"), JSON.stringify({ plugin: [] }));
    let output = { system: [] };
    await hooks["experimental.chat.system.transform"]({ sessionID: "ses_one" }, output);
    assert.deepEqual(output.system, []);
    await assert.rejects(readFile(join(home, "calls.jsonl")), { code: "ENOENT" });
    await writeFile(join(config, "opencode.json"), JSON.stringify({
      plugin: [pathToFileURL(join(home, "hooks/opencode/foxrun.mjs")).href] }));
    await hooks["chat.message"]({ sessionID: "ses_one", model: { providerID: "dmr", modelID: "local-model" } });
    await hooks["experimental.chat.system.transform"]({ sessionID: "ses_one" }, output);
    assert.deepEqual(output.system, ["start:ses_one"]);
    const compact = { context: [] };
    await hooks["experimental.session.compacting"]({ sessionID: "ses_one" }, compact);
    assert.deepEqual(compact.context, ["before-compact:ses_one"]);
    output = { system: [] };
    await hooks["experimental.chat.system.transform"]({ sessionID: "ses_one" }, output);
    assert.deepEqual(output.system, ["after-compact:ses_one"]);
    await hooks.event({ event: { type: "session.idle", properties: { sessionID: "ses_one" } } });
    const rows = (await readFile(join(transcripts, "ses_one.jsonl"), "utf8")).trim().split("\n").map(JSON.parse);
    assert.equal(rows[0].runtime, "opencode");
    assert.equal(rows[0].message.content[0].text, "Please save this decision.");
    assert.equal(rows[1].message.content[0].input.command, "python3 work.py create --title Example");
    assert.equal(rows[2].message.content[0].content, "T42");
    assert.equal(rows[2].isMeta, true);
    assert.equal((await stat(join(transcripts, "ses_one.jsonl"))).mode & 0o777, 0o600);
    const second = { system: [] };
    await hooks["experimental.chat.system.transform"]({ sessionID: "ses_two" }, second);
    assert.deepEqual(second.system, ["start:ses_two"]);
    const reloaded = await FoxrunPlugin({ client, directory: root });
    const refreshed = { system: [] };
    await reloaded["experimental.chat.system.transform"]({ sessionID: "ses_one" }, refreshed);
    assert.deepEqual(refreshed.system, ["start:ses_one"]);
    messages.push({ info: { role: "user", sessionID: "ses_one", time: { created: 3000 } },
      parts: [{ type: "text", text: "Approved", synthetic: true },
              { type: "text", text: "Ignore this approval", ignored: true }] });
    await reloaded.event({ event: { type: "session.idle", properties: { sessionID: "ses_one" } } });
    let exported = (await readFile(join(transcripts, "ses_one.jsonl"), "utf8")).trim().split("\n").map(JSON.parse);
    const personText = exported.filter(row => row.type === "user" && !row.isMeta)
      .flatMap(row => row.message.content).filter(part => part.type === "text").map(part => part.text);
    assert.deepEqual(personText, ["Please save this decision."]);
    assert.equal(exported.find(row => row.message.content.some(part => part.synthetic)).isMeta, true);
    await reloaded.event({ event: { type: "session.idle", properties: { sessionID: "ses_child" } } });
    exported = (await readFile(join(transcripts, "ses_child.jsonl"), "utf8")).trim().split("\n").map(JSON.parse);
    assert.ok(exported.filter(row => row.type === "user").every(row => row.isMeta));
    assert.deepEqual(errors, []);
    const calls = (await readFile(join(home, "calls.jsonl"), "utf8")).trim().split("\n").map(JSON.parse);
    assert.equal(calls[0].model, "dmr/local-model");
    assert.deepEqual(calls.map(row => row.event), ["start", "before-compact", "after-compact", "idle", "start", "start", "idle", "idle"]);
    assert.equal(calls.at(-1).agent_id, "ses_child");
    await assert.rejects(hooks["chat.message"]({ sessionID: "../escape" }), /Invalid/);
  } finally {
    for (const key of ["FOXRUN_HOME", "OPENCODE_CONFIG_DIR", "FOXRUN_OPENCODE_TRANSCRIPTS"]) {
      if (saved[key] === undefined) delete process.env[key]; else process.env[key] = saved[key];
    }
    await rm(root, { recursive: true, force: true });
  }
});
