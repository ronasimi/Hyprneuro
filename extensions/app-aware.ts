/**
 * Hyprneuro application-aware Pi Durable adapter (versioned: app-context/1).
 *
 * This is a NARROW bridge, not a second agent runtime. It exposes the
 * sidecar's model-free application context, tiered memory, staged skills and
 * durable-task state as compact Pi tools. Durable task EXECUTION is delegated
 * to Pi's native `subagents` (Pi Durable) runtime; these tools only prepare
 * context and persist task/memory state in the local sidecar.
 *
 * The sidecar must be running with `--assistant-enabled` (which requires
 * `--watch-hyprland`). No LLM inference happens on focus; no screenshots are
 * captured by these tools.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { connect } from "node:net";
import { join } from "node:path";

const MAX_REPLY = 256 * 1024;

async function sidecar(message: Record<string, unknown>, signal?: AbortSignal): Promise<any> {
  const runtime = process.env.XDG_RUNTIME_DIR;
  if (!runtime || !runtime.startsWith("/")) throw new Error("No local runtime directory");
  return await new Promise((resolve, reject) => {
    const sock = connect(join(runtime, "hyprharness", "sidecar.sock"));
    let buf = Buffer.alloc(0);
    let completed = false;
    const finish = (err?: Error, value?: unknown) => {
      if (completed) return;
      completed = true;
      signal?.removeEventListener("abort", abort);
      sock.destroy();
      if (err) reject(err); else resolve(value);
    };
    const abort = () => finish(new Error("Sidecar query cancelled"));
    if (signal?.aborted) return abort();
    signal?.addEventListener("abort", abort, { once: true });
    sock.setTimeout(8000, () => finish(new Error("Sidecar timed out")));
    sock.on("error", (error) => finish(error));
    sock.on("connect", () => sock.write(JSON.stringify(message) + "\n"));
    sock.on("data", (chunk) => {
      buf = Buffer.concat([buf, chunk]);
      if (buf.length > MAX_REPLY) return finish(new Error("Oversized sidecar result"));
      const idx = buf.indexOf(10);
      if (idx < 0) return;
      try {
        const packet = JSON.parse(buf.subarray(0, idx).toString("utf8"));
        if (!packet.ok) return finish(new Error(String(packet.error ?? "Sidecar rejected request")));
        finish(undefined, packet.result);
      } catch { finish(new Error("Invalid sidecar response")); }
    });
    sock.on("end", () => finish(new Error("Sidecar disconnected")));
  });
}

const result = (value: unknown) => {
  const encoded = JSON.stringify(value);
  return {
    content: [{ type: "text" as const, text: encoded.length <= 12000 ? encoded :
      encoded.slice(0, 11900) + "\n[Truncated to 12000 characters.]" }],
    details: { source: "hyprneuro-adapter", schema: "app-context/1", truncated: encoded.length > 12000 },
  };
};

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "hyprneuro_app_context",
    label: "Focused + recent application context",
    description: "Read the model-free application context Hyprneuro tracks: the focused window and a bounded LRU of recent applications (id, class, workspace, title, focus recency). No LLM inference or screenshot is involved. Use to ground a durable task in the current application before acting.",
    promptSnippet: "Get the current focused application and recent-app context",
    parameters: Type.Object({
      role: Type.Optional(Type.Union([Type.Literal("text"), Type.Literal("omni")])),
    }),
    async execute(_id, params, signal) {
      return result(await sidecar({ action: "app_context", role: params.role ?? "text" }, signal));
    },
  });

  pi.registerTool({
    name: "hyprneuro_memory",
    label: "Tiered durable memory",
    description: "Recall or remember scoped records in Hyprneuro's tiered memory (task / app / project / global). Use `recall` to retrieve only the relevant scoped records for a task; use `remember` to persist a durable fact. Cross-scope promotion is a separate, approval-gated operation and is NOT performed by `remember`.",
    promptSnippet: "Recall or store scoped task/app/project/global memory",
    parameters: Type.Object({
      action: Type.Union([Type.Literal("recall"), Type.Literal("remember")]),
      scope: Type.Union([Type.Literal("task"), Type.Literal("app"), Type.Literal("project"), Type.Literal("global")]),
      key: Type.String({ maxLength: 128 }),
      value: Type.Optional(Type.Unknown({ description: "Required for remember" })),
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 50 })),
      task_id: Type.Optional(Type.String({ maxLength: 128 })),
      app_id: Type.Optional(Type.String({ maxLength: 128 })),
      project_id: Type.Optional(Type.String({ maxLength: 128 })),
    }),
    async execute(_id, params, signal) {
      const action = params.action === "recall" ? "memory_recall" : "memory_remember";
      const payload: Record<string, unknown> = { action, scope: params.scope, key: params.key };
      if (params.value !== undefined) payload.value = params.value;
      if (params.limit !== undefined) payload.limit = params.limit;
      if (params.task_id) payload.task_id = params.task_id;
      if (params.app_id) payload.app_id = params.app_id;
      if (params.project_id) payload.project_id = params.project_id;
      return result(await sidecar(payload, signal));
    },
  });

  pi.registerTool({
    name: "hyprneuro_skills",
    label: "Staged application skills",
    description: "Discover compact skill manifests for the focused/recent applications (`discover`), list all known skills (`list`), or load one full skill body + tool schema only when a task needs it (`load`). Manifests stay small; the full body is loaded on demand to keep the initial tool surface compact.",
    promptSnippet: "Discover or load a staged application skill",
    parameters: Type.Object({
      action: Type.Union([Type.Literal("discover"), Type.Literal("load"), Type.Literal("list")]),
      app_id: Type.Optional(Type.String({ maxLength: 120 })),
    }),
    async execute(_id, params, signal) {
      const action = params.action === "discover" ? "skill_discover"
        : params.action === "load" ? "skill_load" : "skill_list";
      const payload: Record<string, unknown> = { action };
      if (params.app_id) payload.app_id = params.app_id;
      return result(await sidecar(payload, signal));
    },
  });

  pi.registerTool({
    name: "hyprneuro_tasks",
    label: "Durable task state",
    description: "Create, read, list, or update Hyprneuro durable-task records (goal, scope, status, state). Tasks belong to goals, not windows, so they survive interface dismissal and can span applications. Execution is delegated to the native Pi Durable `subagents` runtime; this tool persists the task record and its state so a run can be resumed. Status transitions are state-only and never launch desktop automation by themselves.",
    promptSnippet: "Create, inspect, list, or update a durable task record",
    parameters: Type.Object({
      action: Type.Union([Type.Literal("create"), Type.Literal("get"), Type.Literal("list"), Type.Literal("update")]),
      goal: Type.Optional(Type.String({ maxLength: 500 })),
      id: Type.Optional(Type.Integer({ minimum: 1 })),
      status: Type.Optional(Type.Union([
        Type.Literal("active"), Type.Literal("suspended"),
        Type.Literal("done"), Type.Literal("failed"), Type.Literal("cancelled"),
      ])),
      state: Type.Optional(Type.Object({}, { additionalProperties: true })),
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 50 })),
    }),
    async execute(_id, params, signal) {
      const action = params.action === "create" ? "task_create"
        : params.action === "get" ? "task_get"
        : params.action === "list" ? "task_list" : "task_update";
      const payload: Record<string, unknown> = { action };
      if (params.goal !== undefined) payload.goal = params.goal;
      if (params.id !== undefined) payload.id = params.id;
      if (params.status) payload.status = params.status;
      if (params.state !== undefined) payload.state = params.state;
      if (params.limit !== undefined) payload.limit = params.limit;
      return result(await sidecar(payload, signal));
    },
  });
}
