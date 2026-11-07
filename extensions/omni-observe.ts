/**
 * Explicit Pi -> local Omni 2B handoff. Background Recall never calls Pi.
 * No screenshots or base64 data pass through the Pi conversation.
 * Requires a separately opt-in sidecar (--allow-ingest --allow-on-demand),
 * plus an interactive per-request confirmation. All image bytes remain RAM-only.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { connect } from "node:net";
import { join } from "node:path";

const MAX_REPLY = 16 * 1024;

async function observe(purpose: "read_text" | "describe" | "both", signal: AbortSignal) {
  // Keep the legacy socket path compatible with existing service installations.
  const runtime = process.env.XDG_RUNTIME_DIR;
  if (!runtime || !runtime.startsWith("/")) throw new Error("XDG_RUNTIME_DIR unavailable");
  const path = join(runtime, "hyprharness", "sidecar.sock");
  return await new Promise<unknown>((resolve, reject) => {
    let complete = false;
    const sock = connect(path);
    let incoming = Buffer.alloc(0);
    const done = (error?: Error, value?: unknown) => {
      if (complete) return;
      complete = true;
      signal?.removeEventListener("abort", abort);
      sock.destroy();
      if (error) reject(error); else resolve(value);
    };
    const abort = () => done(new Error("Observation cancelled"));
    if (signal?.aborted) return abort();
    signal?.addEventListener("abort", abort, { once: true });
    sock.setTimeout(120000, () => done(new Error("Omni observation timed out")));
    sock.on("error", (err) => done(err));
    sock.on("connect", () => sock.write(JSON.stringify({ action: "omni_observe", purpose }) + "\n"));
    sock.on("data", (chunk) => {
      incoming = Buffer.concat([incoming, chunk]);
      if (incoming.length > MAX_REPLY) return done(new Error("Oversized observation reply"));
      const newline = incoming.indexOf(10);
      if (newline < 0) return;
      try {
        const packet = JSON.parse(incoming.subarray(0, newline).toString("utf8"));
        if (!packet.ok) return done(new Error(String(packet.error ?? "Sidecar refused observation")));
        return done(undefined, packet.result);
      } catch {
        return done(new Error("Invalid sidecar response"));
      }
    });
    sock.on("end", () => done(new Error("Sidecar disconnected")));
  });
}

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "omni_observe",
    label: "Observe focused window (Omni)",
    description: "With explicit user approval, ask the local Omni model to read or describe the currently focused window. Persists a time-indexed observation in private SQLite; only a short excerpt enters Pi context.",
    promptSnippet: "Request a consented, on-demand local Omni screenshot for visible UI evidence",
    parameters: Type.Object({
      purpose: Type.Union([Type.Literal("read_text"), Type.Literal("describe"), Type.Literal("both")]),
    }),
    async execute(_id, params, signal, _onUpdate, ctx) {
      if (!ctx.hasUI) throw new Error("A connected approval UI is required for screenshots");
      const allowed = await ctx.ui.confirm(
        "Allow one focused-window screenshot?",
        "Omni will analyze the focused window for: " + params.purpose +
        ". No screenshot files are saved. Only a short text result is given to Pi.",
        { timeout: 60000 },
      );
      if (!allowed) throw new Error("Screenshot denied");
      const value = await observe(params.purpose, signal);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(value) }],
        details: { source: "hyprneuro", untrusted: true },
      };
    },
  });
}
