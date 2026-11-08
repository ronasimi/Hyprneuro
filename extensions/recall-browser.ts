/** Read-only Recall and consented exact-URL restoration via the local sidecar.
 * No browser shell commands, remote APIs, cookies or screenshot storage.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { connect } from "node:net";
import { join } from "node:path";
import { spawn } from "node:child_process";

async function sidecar(message: Record<string, unknown>, signal?: AbortSignal): Promise<any> {
  // Keep the legacy socket path compatible with existing service installations.
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
    sock.setTimeout(5000, () => finish(new Error("Sidecar timed out")));
    sock.on("error", (error) => finish(error));
    sock.on("connect", () => sock.write(JSON.stringify(message) + "\n"));
    sock.on("data", (chunk) => {
      buf = Buffer.concat([buf, chunk]);
      if (buf.length > 256 * 1024) return finish(new Error("Oversized Recall result"));
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

function timeRange(period: string): { start_ms?: number; end_ms?: number } {
  const now = new Date();
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (period === "last_24h") return { start_ms: Date.now() - 86_400_000 };
  if (period === "today") return { start_ms: midnight.getTime() };
  if (period === "yesterday") {
    const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
    return { start_ms: yesterday.getTime(), end_ms: midnight.getTime() - 1 };
  }
  if (period === "last_night") {
    const evening = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1, 18);
    const morning = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 6);
    return { start_ms: evening.getTime(), end_ms: Math.min(Date.now(), morning.getTime()) };
  }
  return {};
}

async function openExactUrl(url: string, signal?: AbortSignal): Promise<void> {
  const parsed = new URL(url);
  if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname || parsed.username || parsed.password) {
    throw new Error("Refusing unsafe browser URL");
  }
  await new Promise<void>((resolve, reject) => {
    const child = spawn("xdg-open", [url], { stdio: "ignore", shell: false });
    const onAbort = () => { child.kill(); reject(new Error("Browser launch cancelled; outcome unknown")); };
    signal?.addEventListener("abort", onAbort, { once: true });
    const timeout = setTimeout(() => { child.kill(); reject(new Error("Browser opener timed out; outcome unknown")); }, 8000);
    const finish = (err?: Error) => {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", onAbort);
      if (err) reject(err); else resolve();
    };
    child.once("error", (error) => finish(error));
    child.once("close", (code) => finish(code === 0 ? undefined : new Error(`Browser opener exited ${code}`)));
  });
}

const result = (value: unknown) => {
  const encoded = JSON.stringify(value);
  return {
    content: [{ type: "text" as const, text: encoded.length <= 12000 ? encoded :
      encoded.slice(0, 11900) + "\n[Truncated to 12000 characters; request fewer results for details.]" }],
    details: { source: "hyprneuro-recall", truncated: encoded.length > 12000 },
  };
};

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "recall_search",
    label: "Search local screen/browser history",
    description: "Search time-indexed local Recall observations and verified Chrome pages. Read-only; returns untrusted metadata without screenshots (20 rows, 12000-character tool output cap).",
    promptSnippet: "Find previous tabs, apps and visual observations by local time or title",
    parameters: Type.Object({
      query: Type.Optional(Type.String({ maxLength: 300 })),
      period: Type.Optional(Type.Union([
        Type.Literal("all"), Type.Literal("last_night"), Type.Literal("yesterday"),
        Type.Literal("today"), Type.Literal("last_24h"),
      ])),
      start_ms: Type.Optional(Type.Integer({ minimum: 1, description: "Exact inclusive Unix milliseconds; overrides period start" })),
      end_ms: Type.Optional(Type.Integer({ minimum: 1, description: "Exact inclusive Unix milliseconds; overrides period end" })),
      order: Type.Optional(Type.Union([Type.Literal("recent"), Type.Literal("relevance")])),
      match: Type.Optional(Type.Union([Type.Literal("terms"), Type.Literal("phrase"), Type.Literal("prefix"), Type.Literal("fuzzy")])),
      semantic: Type.Optional(Type.Boolean({ description: "Requires explicit local embeddings configuration; searches at most 50 recent filtered records" })),
      source: Type.Optional(Type.Union([Type.Literal("chrome"), Type.Literal("omni"), Type.Literal("hyprland"), Type.Literal("journal"), Type.Literal("network"), Type.Literal("resource")])),
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 20 })),
    }),
    async execute(_id, params, signal) {
      const value = await sidecar({ action: "search", query: params.query ?? "",
        source: params.source, limit: params.limit ?? 10, order: params.order ?? "recent",
        match: params.match ?? "terms", semantic: params.semantic ?? false,
        ...timeRange(params.period ?? "all"),
        ...(params.start_ms === undefined ? {} : { start_ms: params.start_ms }),
        ...(params.end_ms === undefined ? {} : { end_ms: params.end_ms }) }, signal);
      return result({ untrusted: true, results: value });
    },
  });

  pi.registerTool({
    name: "recall_open_page",
    label: "Open an exact saved browser page",
    description: "Look up an authenticated Chrome URL by local Recall ID and request explicit user approval before opening it. Never infer a page address from OCR.",
    promptSnippet: "Reopen a previously visited, verified URL with explicit approval",
    parameters: Type.Object({ id: Type.Integer({ minimum: 1 }) }),
    async execute(_id, params, signal, _onUpdate, ctx) {
      if (!ctx.hasUI) throw new Error("Browser navigation requires an interactive approval UI");
      const page = await sidecar({ action: "page_url", id: params.id }, signal);
      if (page.id !== params.id || page.requires_approval !== true || typeof page.url !== "string") {
        throw new Error("Missing verified browser provenance");
      }
      const parsed = new URL(page.url);
      if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname || parsed.username || parsed.password) {
        throw new Error("Refusing unsafe URL");
      }
      const permitted = await ctx.ui.confirm(
        "Open this exact saved page?",
        `Local Recall record #${params.id}\n\n${page.url}\n\nThis opens your browser. Continue?`,
        { timeout: 60_000 },
      );
      if (!permitted) throw new Error("Browser navigation denied");
      const since = Date.now();
      await openExactUrl(page.url, signal);
      let confirmed = false;
      for (let i = 0; i < 6; i++) {
        const check = await sidecar({ action: "verify_navigation", id: params.id, since_ms: since }, signal);
        if (check.verified === true) { confirmed = true; break; }
        if (i < 5) await new Promise<void>((done) => setTimeout(done, 800));
      }
      return result({ launch_requested: true, browser_event_verified: confirmed,
        id: params.id, url_preview: parsed.origin + parsed.pathname,
        note: confirmed ? "Chrome reported an active tab with the exact saved URL" :
          "Browser launch returned success; no Chrome navigation confirmation yet" });
    },
  });

  pi.registerTool({
    name: "recall_alerts",
    label: "Recent system alerts",
    description: "On user request, inspect recent journal/network/resource alerts, D1 scores and desktop-notification outcomes. Read-only; alerts never automatically wake Pi or inject session context.",
    promptSnippet: "Inspect stored system alerts and D1 notification decisions when asked",
    parameters: Type.Object({
      limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 50 })),
    }),
    async execute(_id, params, signal) {
      const value = await sidecar({ action: "alerts", limit: params.limit ?? 20 }, signal);
      return result({ untrusted: true, alerts: value });
    },
  });
}
