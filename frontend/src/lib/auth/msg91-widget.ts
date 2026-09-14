export type OtpWidgetConfig = { enabled: false } | { enabled: true; widgetId: string; tokenAuth: string };

type Callback = (value: unknown) => void;
type Msg91Window = Window & {
  initSendOTP?: (configuration: Record<string, unknown>) => void | Promise<void>;
  sendOtp?: (identifier: string, success?: Callback, failure?: Callback) => void;
  verifyOtp?: (otp: string, success?: Callback, failure?: Callback) => unknown;
};

type WidgetState = {
  accessToken?: string;
  initialization?: Promise<Msg91Window>;
  pendingSuccess?: Callback;
  pendingFailure?: Callback;
};

type TokenMatch = { token: string; path: string };

let scriptPromise: Promise<void> | undefined;
const widgetStates = new WeakMap<object, WidgetState>();
const SDK_READY_TIMEOUT_MS = 5000;

export async function loadOtpWidgetConfig(): Promise<OtpWidgetConfig> {
  const response = await fetch("/api/otp-widget/config", { cache: "no-store" });
  if (!response.ok) throw new Error("Mobile verification is temporarily unavailable.");
  return response.json() as Promise<OtpWidgetConfig>;
}

function loadScript() {
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise<void>((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>('script[src="https://verify.msg91.com/otp-provider.js"]');
    if (existing && (window as Msg91Window).initSendOTP) return resolve();
    existing?.remove();
    const script = document.createElement("script");
    script.src = "https://verify.msg91.com/otp-provider.js";
    script.async = true;
    script.addEventListener("load", () => resolve(), { once: true });
    script.addEventListener("error", () => reject(new Error("Mobile verification could not be loaded.")), { once: true });
    document.head.appendChild(script);
  });
  return scriptPromise.catch((error) => {
    scriptPromise = undefined;
    throw error;
  });
}

function waitForSdkMethods(api: Msg91Window) {
  return new Promise<void>((resolve, reject) => {
    const startedAt = Date.now();
    const check = () => {
      if (typeof api.sendOtp === "function" && typeof api.verifyOtp === "function") {
        resolve();
        return;
      }
      if (Date.now() - startedAt >= SDK_READY_TIMEOUT_MS) {
        reject(new Error("Mobile verification could not be initialized."));
        return;
      }
      window.setTimeout(check, 25);
    };
    check();
  });
}

async function initialize(config: Extract<OtpWidgetConfig, { enabled: true }>) {
  let state = widgetStates.get(config);
  if (!state) {
    state = {};
    widgetStates.set(config, state);
  }
  if (!state.initialization) {
    const currentState = state;
    state.initialization = (async () => {
      await loadScript();
      try {
        const api = window as Msg91Window;
        if (!api.initSendOTP) throw new Error("MSG91 SDK is unavailable.");
        const success: Callback = (data) => {
          const accessToken = findAccessToken(data);
          if (accessToken) currentState.accessToken = accessToken.token;
          currentState.pendingSuccess?.(data);
        };
        const failure: Callback = (error) => currentState.pendingFailure?.(error);
        await api.initSendOTP({
          widgetId: config.widgetId,
          tokenAuth: config.tokenAuth,
          exposeMethods: true,
          success,
          failure,
        });
        await waitForSdkMethods(api);
        return api;
      } catch {
        currentState.initialization = undefined;
        throw new Error("Mobile verification could not be initialized.");
      }
    })();
  }
  return { api: await state.initialization, state };
}

function callbackCall(call: (success: Callback, failure: Callback) => void) {
  return new Promise<unknown>((resolve, reject) => call(resolve, () => reject(new Error("Mobile verification was not completed."))));
}

export async function sendMsg91Otp(config: Extract<OtpWidgetConfig, { enabled: true }>, mobile: string) {
  const { api } = await initialize(config);
  if (!api.sendOtp) throw new Error("Mobile verification could not be initialized.");
  await callbackCall((success, failure) => api.sendOtp?.(`91${mobile}`, success, failure));
}

function findAccessToken(value: unknown, path = "$", seen = new Set<object>()): TokenMatch | undefined {
  if (typeof value === "string") {
    return /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(value)
      ? { token: value, path }
      : undefined;
  }
  if (!value || typeof value !== "object") return undefined;
  if (seen.has(value)) return undefined;
  seen.add(value);
  for (const [key, child] of Object.entries(value)) {
    const childPath = `${path}.${key}`;
    if (["access-token", "access_token", "token"].includes(key) && typeof child === "string") {
      return { token: child, path: childPath };
    }
    const nested = findAccessToken(child, childPath, seen);
    if (nested) return nested;
  }
  return undefined;
}

export async function verifyMsg91Otp(config: Extract<OtpWidgetConfig, { enabled: true }>, otp: string) {
  const { api, state } = await initialize(config);
  if (!api.verifyOtp) throw new Error("Mobile verification could not be initialized.");
  state.accessToken = undefined;
  const accessToken = await new Promise<string>((resolve, reject) => {
    const timeout = window.setTimeout(
      () => reject(new Error("Mobile verification did not return a valid access token.")),
      5000,
    );
    const success: Callback = (data) => {
      const token = state.accessToken ?? findAccessToken(data)?.token;
      if (token) {
        window.clearTimeout(timeout);
        resolve(token);
      }
    };
    const failure: Callback = () => {
      window.clearTimeout(timeout);
      reject(new Error("Mobile verification was not completed."));
    };
    state.pendingSuccess = success;
    state.pendingFailure = failure;
    api.verifyOtp?.(otp, success, failure);
  }).finally(() => {
    state.pendingSuccess = undefined;
    state.pendingFailure = undefined;
  });
  return accessToken;
}
