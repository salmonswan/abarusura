// Pipeline guard. Asks `devpipeline guard` about every tool call and refuses what it refuses.
// Fails closed: if the guard is missing, crashes or gives bad input, the call is refused.
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event: any) => {
    try {
      // Send only what the guard reads. A write input holds the whole file, which can be too big for argv.
      const tool = String(event.toolName ?? "");
      const inp = event.input ?? {};
      const small: Record<string, unknown> = {};
      if (tool === "bash") small.command = inp.command;
      else if (tool === "write" || tool === "edit") {
        if ("path" in inp) small.path = inp.path;
        if ("file_path" in inp) small.file_path = inp.file_path;
      }
      const call = JSON.stringify({ tool, input: small });
      const r = await pi.exec("devpipeline", ["guard", "--call", call]);
      if (r.code === 0) return;
      if (r.code === 1) {
        const line = String(r.stdout ?? "").trim().split("\n")[0] || "refused by the pipeline guard";
        return { block: true, reason: `REFUSED: ${line}` };
      }
      const err = String(r.stderr ?? "").trim().split("\n")[0] || `exit ${r.code}`;
      return { block: true, reason: `REFUSED: guard could not run: ${err}` };
    } catch (e: any) {
      return { block: true, reason: `REFUSED: guard could not run: ${String(e?.message ?? e).split("\n")[0]}` };
    }
  });
}
