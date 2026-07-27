// Single source of truth for the whitelisted macro commands on the TypeScript side.
// It MUST stay in sync with remote/PROTOCOL.md section 2 and remote/agent/internal/protocol/protocol.go.
// This module has NO dependencies so it can be shared verbatim by the backend and the browser
// frontend (the build copies the compiled ESM output into the web bundle).
//
// The command channel is UNTRUSTED input: this whitelist is the ONLY set of actions a remote client
// can trigger, and it must never grow to accept raw coordinates, keystrokes, scripts, or arbitrary
// preset data. Every command here maps onto the same mechanism a local hotkey/button already uses.

export const COMMAND_TYPES = [
  "PAUSE",
  "RESUME",
  "STOP",
  "SET_ACTIVE_PRESET",
  "QUEUE_PRESET",
] as const;

export type CommandType = (typeof COMMAND_TYPES)[number];

/** Maximum length, in bytes, of a command argument (a preset name). */
export const MAX_ARG_BYTES = 200;

export interface CommandMeta {
  /** Human-readable label for the UI button. */
  readonly label: string;
  /** Whether this command carries a preset-name argument. */
  readonly usesArg: boolean;
  /** Label for the argument input, when usesArg is true. */
  readonly argLabel?: string;
  /** Short description of the effect, for tooltips/help. */
  readonly description: string;
}

export const COMMAND_META: Readonly<Record<CommandType, CommandMeta>> = {
  PAUSE: {
    label: "Pause",
    usesArg: false,
    description: "Pause the running macro (same effect as the F9 hotkey).",
  },
  RESUME: {
    label: "Resume",
    usesArg: false,
    description: "Resume a paused macro (same effect as the F9 hotkey).",
  },
  STOP: {
    label: "Stop",
    usesArg: false,
    description: "Stop the macro (same effect as the Escape emergency stop).",
  },
  SET_ACTIVE_PRESET: {
    label: "Set active preset",
    usesArg: true,
    argLabel: "Preset name",
    description: "Choose which preset runs on the next start. Does not interrupt a run in progress.",
  },
  QUEUE_PRESET: {
    label: "Queue preset",
    usesArg: true,
    argLabel: "Preset name",
    description: "Switch presets mid-run at the next cycle boundary. Only meaningful while running.",
  },
};

export function isValidCommandType(t: unknown): t is CommandType {
  return typeof t === "string" && (COMMAND_TYPES as readonly string[]).includes(t);
}

export function commandUsesArg(t: CommandType): boolean {
  return COMMAND_META[t].usesArg;
}

export interface CommandValidationResult {
  ok: boolean;
  error?: string;
}

/**
 * Validates a command payload received from a browser client before it is enqueued for a device.
 * Enforces the whitelist and the argument rules. The macro re-validates the preset name against its
 * own state, so this only guards shape/length; it does not (and cannot) verify the preset exists.
 */
export function validateCommand(input: { type: unknown; arg?: unknown }): CommandValidationResult {
  if (!isValidCommandType(input.type)) {
    return { ok: false, error: "Unknown command type." };
  }
  const type = input.type;
  const usesArg = commandUsesArg(type);
  const arg = input.arg;

  if (usesArg) {
    if (typeof arg !== "string" || arg.trim() === "") {
      return { ok: false, error: `${COMMAND_META[type].label} requires a preset name.` };
    }
    if (new TextEncoder().encode(arg).length > MAX_ARG_BYTES) {
      return { ok: false, error: `Preset name is too long (max ${MAX_ARG_BYTES} bytes).` };
    }
  } else if (arg !== undefined && arg !== null && arg !== "") {
    return { ok: false, error: `${COMMAND_META[type].label} does not take an argument.` };
  }

  return { ok: true };
}
