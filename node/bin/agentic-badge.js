// Report opencode's attention state to the strip, the way the Claude Code
// hooks and the Codex notify program already do.
//
// Everything routes through one `event` hook, so this is a switch over the
// Event union rather than several handlers. Event names are taken from the
// installed SDK, not the docs: this build has permission.updated, not the
// permission.asked the docs describe.
//
//   permission.updated  -> ask   (an agent wants you; this one pages a phone)
//   permission.replied  -> busy  (answered, back to work)
//   session.status busy -> busy
//   session.idle        -> done
//   session.error       -> ask   (stuck is a kind of waiting)
//
// Badges key on the tmux session, which agentic-badge reads for itself, so a
// subagent and its root land on the same badge. Subagent idles are therefore
// not filtered: an early `done` is corrected by the next `busy`, which is a
// better trade than an SDK lookup per event against an API this build does
// not clearly expose.
import { spawn } from "child_process";
import { homedir } from "os";
import { join } from "path";

const BADGE = join(homedir(), ".agentic/bin/agentic-badge");

// opencode fires idle after every tool round-trip, so a run of them would
// flap the badge between done and busy. Settle before believing it.
const IDLE_SETTLE_MS = 1500;
let pending = null;
let last = null;

function emit(state) {
  if (state === last) return;          // the badge file only needs changes
  last = state;
  try {
    spawn(BADGE, [state], { stdio: "ignore", detached: true }).unref();
  } catch {
    /* the node may not be a fleet node; never take opencode down for this */
  }
}

function settleIdle() {
  clearTimeout(pending);
  // `session.idle` fires between tool round-trips as well as at the end, so a
  // naive emit flaps. But a short run exits milliseconds after going idle,
  // taking any pending timer with it -- so record `done` now and let a later
  // `busy` correct it, rather than waiting for a settle that may never run.
  emit("done");
  pending = setTimeout(() => emit("done"), IDLE_SETTLE_MS);
}

function cancelIdle() {
  clearTimeout(pending);
  pending = null;
}

export const AgenticBadge = async () => ({
  event: async ({ event }) => {
    switch (event?.type) {
      case "permission.updated":
        cancelIdle();
        emit("ask");
        break;
      case "permission.replied":
        cancelIdle();
        emit("busy");
        break;
      case "session.status":
        if (event.properties?.status?.type === "busy") {
          cancelIdle();
          emit("busy");
        } else if (event.properties?.status?.type === "idle") {
          settleIdle();
        }
        break;
      case "session.idle":
        settleIdle();
        break;
      case "session.error":
        cancelIdle();
        emit("ask");
        break;
    }
  },
});
