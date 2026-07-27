type Resolver = () => void;

/**
 * In-process notification fan-out for the single-node MVP. Multi-node deployments need a shared
 * notification bus; that is intentionally deferred to a later phase.
 */
export class DeviceNotifier {
  private readonly waiters = new Map<string, Set<Resolver>>();

  /** Wakes every current long-poll waiter for a device. */
  notify(deviceId: string): void {
    const deviceWaiters = this.waiters.get(deviceId);
    if (deviceWaiters === undefined) return;
    for (const resolve of [...deviceWaiters]) resolve();
  }

  /** Resolves on notification, timeout, or abort, and never rejects. */
  wait(deviceId: string, timeoutMs: number, signal?: AbortSignal): Promise<void> {
    return new Promise((resolve) => {
      let settled = false;
      const waiters = this.waiters.get(deviceId) ?? new Set<Resolver>();
      this.waiters.set(deviceId, waiters);

      const settle = (): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        signal?.removeEventListener("abort", settle);
        waiters.delete(settle);
        if (waiters.size === 0) this.waiters.delete(deviceId);
        resolve();
      };

      const safeTimeout = Math.max(0, timeoutMs);
      const timeout = setTimeout(settle, safeTimeout);
      waiters.add(settle);
      if (signal?.aborted) settle(); else signal?.addEventListener("abort", settle, { once: true });
    });
  }
}

export const deviceNotifier = new DeviceNotifier();
