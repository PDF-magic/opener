// Explicit, fail-closed extension initialization lifecycle (opener-0580).
// This module has no import-time browser, native, storage or filesystem effects.
// Integrations must supply trusted startup steps and their rollback functions.

export const INITIALIZATION_ERROR_CODES = Object.freeze({
  UNAVAILABLE: "INITIALIZATION_UNAVAILABLE",
  STARTUP_FAILED: "INITIALIZATION_FAILED",
  CLEANUP_FAILED: "INITIALIZATION_CLEANUP_FAILED"
});

const MAX_STEPS = 16;

function snapshot(phase, errorCode) {
  return Object.freeze({
    phase,
    errorCode,
    scannerVerified: false,
    authorizesOpen: false
  });
}

function validatedSteps(input) {
  if (!Array.isArray(input) || input.length > MAX_STEPS) {
    throw new TypeError("Invalid extension initialization steps");
  }
  const steps = [];
  try {
    for (let i = 0; i < input.length; i++) {
      // Do not execute caller-defined property getters or accept sparse lists.
      const descriptor = Object.getOwnPropertyDescriptor(input, String(i));
      if (!descriptor || typeof descriptor.value !== "function") {
        throw new TypeError("Invalid extension initialization steps");
      }
      steps.push(descriptor.value);
    }
  } catch {
    throw new TypeError("Invalid extension initialization steps");
  }
  return steps;
}

async function disposeReverse(disposers) {
  let succeeded = true;
  for (let i = disposers.length - 1; i >= 0; i--) {
    try {
      await disposers[i]();
    } catch {
      // Continue undoing all acquired resources, even if one cleanup fails.
      succeeded = false;
    }
  }
  return succeeded;
}

/**
 * Construct a dormant initializer with optional trusted startup steps.
 * Each step must return (or resolve to) a cleanup function. A step that
 * partially acquires resources and then fails must undo its own partial work.
 *
 * start() and stop() are explicit; imports never trigger initialization.
 * Errors are reduced to fixed codes and cannot expose native paths or
 * document data. An unsuccessful attempt cannot be retried implicitly;
 * callers must construct a new controller after addressing the cause.
 */
export function createExtensionInitializer(initializers = []) {
  const steps = validatedSteps(initializers);
  let phase = "idle";
  let errorCode = null;
  let disposers = [];
  let startPromise = null;
  let stopPromise = null;
  let stopRequested = false;

  function state() {
    return snapshot(phase, errorCode);
  }

  function start() {
    if (startPromise) return startPromise;
    if (phase !== "idle") return Promise.resolve(state());
    if (steps.length === 0) {
      phase = "failed";
      errorCode = INITIALIZATION_ERROR_CODES.UNAVAILABLE;
      return Promise.resolve(state());
    }

    phase = "initializing";
    startPromise = (async () => {
      const acquired = [];
      try {
        for (const initialize of steps) {
          if (stopRequested) break;
          const dispose = await initialize();
          if (typeof dispose !== "function") {
            throw new TypeError("An extension startup step needs cleanup");
          }
          acquired.push(dispose);
        }

        if (stopRequested) {
          const cleaned = await disposeReverse(acquired);
          phase = cleaned ? "stopped" : "failed";
          errorCode = cleaned ? null : INITIALIZATION_ERROR_CODES.CLEANUP_FAILED;
        } else {
          disposers = acquired;
          phase = "initialized";
        }
      } catch {
        const cleaned = await disposeReverse(acquired);
        phase = "failed";
        errorCode = cleaned
          ? INITIALIZATION_ERROR_CODES.STARTUP_FAILED
          : INITIALIZATION_ERROR_CODES.CLEANUP_FAILED;
      }
      return state();
    })();
    return startPromise;
  }

  function stop() {
    if (stopPromise) return stopPromise;
    stopRequested = true;
    stopPromise = (async () => {
      if (startPromise) await startPromise;
      if (disposers.length !== 0) {
        const toDispose = disposers;
        disposers = [];
        const cleaned = await disposeReverse(toDispose);
        phase = cleaned ? "stopped" : "failed";
        errorCode = cleaned ? null : INITIALIZATION_ERROR_CODES.CLEANUP_FAILED;
      } else if (phase !== "failed") {
        phase = "stopped";
        errorCode = null;
      }
      return state();
    })();
    return stopPromise;
  }

  return Object.freeze({ state, start, stop });
}
