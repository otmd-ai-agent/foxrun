import { tool } from "@opencode-ai/plugin";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { join } from "node:path";

const exec = promisify(execFile);
const slug = tool.schema.string().regex(/^[a-z0-9][a-z0-9-]{0,62}$/);
const personName = tool.schema.string().regex(/^[A-Za-z][A-Za-z0-9_-]*$/);
const threadArgs = {
  seat: slug.describe("chief-of-staff, lead, or another seat from setup status"),
  workspace: slug.describe("The workspace chosen by the person"),
  emoji: tool.schema.string().optional().describe("Omit to use the seat's default emoji"),
};
async function run(action: string, args: Record<string, string | undefined> = {}) {
  if (args.workspace !== undefined) slug.parse(args.workspace);
  if (args.seat !== undefined) slug.parse(args.seat);
  const source = process.env.FOXRUN_PRODUCT_SOURCE;
  if (!source) throw new Error("Foxrun's local source is not configured.");
  const command = [join(source, "codespaces/onboarding.py"), action];
  for (const [key, value] of Object.entries(args)) if (value !== undefined) command.push(`--${key}`, value);
  try {
    const result = await exec("python3", command, { timeout: 180000, maxBuffer: 1024 * 1024 });
    return result.stdout.trim();
  } catch (error: any) {
    throw new Error(error.stdout?.trim() || error.stderr?.trim() || error.message);
  }
}
export const status = tool({
  description: "Read Foxrun setup state. Before installation, reports installed=false. Afterwards, inspect one part at a time.",
  args: { part: tool.schema.enum(["questions", "threads", "hooks", "backup"]).optional() },
  async execute(args) { return run("status", args); },
});
export const install = tool({
  description: "Install the real Foxrun checkout with the person's answers. Requires approval; retains a full log and returns the doctor summary.",
  args: { person: personName, workspace: slug },
  async execute(args, context) {
    personName.parse(args.person); slug.parse(args.workspace);
    await context.ask({ permission: "foxrun_install", patterns: [args.workspace], always: [], metadata: args });
    return run("install", args);
  },
});
export const doctor = tool({
  description: "Check the installed Foxrun product and return its doctor summary.",
  args: {}, async execute() { return run("doctor"); },
});
export const plan = tool({
  description: "Plan a real agent thread without creating it. Show its title, workspace, and model for approval.",
  args: threadArgs, async execute(args) { return run("plan", args); },
});
export const make = tool({
  description: "Create the approved agent thread and queue its boot. Use the same arguments as its approved plan. Queued does not mean boot completed.",
  args: threadArgs,
  async execute(args, context) {
    const planned = JSON.parse(await run("plan", args)).result;
    await context.ask({ permission: "foxrun_make", patterns: [args.seat + "@" + args.workspace], always: [],
      metadata: { ...args, title: planned.title, cwd: planned.cwd, model: planned.model } });
    return run("make", args);
  },
});
export const memory = tool({
  description: "Enable Foxrun's session memory hooks after the person agrees. Preserves other settings and reports backups.",
  args: {},
  async execute(args, context) {
    await context.ask({ permission: "foxrun_memory", patterns: ["opencode"], always: [], metadata: {} });
    return run("memory");
  },
});
