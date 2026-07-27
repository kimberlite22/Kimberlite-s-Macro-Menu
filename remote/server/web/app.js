const state = {
  view: "loading",
  user: null,
  devices: [],
  commands: null,
  selectedId: null,
  status: null,
  statusError: "",
  logs: [],
  lastLogId: 0,
  logsError: "",
  commandInFlight: false,
  loginMode: "signin",
  twoFactorMode: "totp",
  securitySetup: null,
  audit: [],
  auditError: "",
  deviceTimer: null,
  statusTimer: null,
  logsTimer: null,
  selectionToken: 0,
  pairCode: null,
  noticeTimer: null
};

const elements = {
  loadingView: document.querySelector("#loading-view"),
  loginView: document.querySelector("#login-view"),
  twoFactorView: document.querySelector("#two-factor-view"),
  dashboardView: document.querySelector("#dashboard-view"),
  authForm: document.querySelector("#auth-form"),
  authError: document.querySelector("#auth-error"),
  authSubmit: document.querySelector("#auth-submit"),
  nameField: document.querySelector("#name-field"),
  nameInput: document.querySelector("#name-input"),
  emailInput: document.querySelector("#email-input"),
  passwordInput: document.querySelector("#password-input"),
  signInMode: document.querySelector("#sign-in-mode"),
  signUpMode: document.querySelector("#sign-up-mode"),
  twoFactorForm: document.querySelector("#two-factor-form"),
  twoFactorCodeLabel: document.querySelector("#two-factor-code-label"),
  twoFactorCodeInput: document.querySelector("#two-factor-code-input"),
  twoFactorError: document.querySelector("#two-factor-error"),
  twoFactorSubmit: document.querySelector("#two-factor-submit"),
  backupCodeToggle: document.querySelector("#backup-code-toggle"),
  backToSignIn: document.querySelector("#back-to-sign-in"),
  userEmail: document.querySelector("#user-email"),
  signOutButton: document.querySelector("#sign-out-button"),
  deviceNameInput: document.querySelector("#device-name-input"),
  addDeviceButton: document.querySelector("#add-device-button"),
  pairPanel: document.querySelector("#pair-panel"),
  pairCode: document.querySelector("#pair-code"),
  pairExpiry: document.querySelector("#pair-expiry"),
  pairCommand: document.querySelector("#pair-command"),
  copyCodeButton: document.querySelector("#copy-code-button"),
  pairMessage: document.querySelector("#pair-message"),
  deviceList: document.querySelector("#device-list"),
  emptyDevices: document.querySelector("#empty-devices"),
  devicesError: document.querySelector("#devices-error"),
  devicePanel: document.querySelector("#device-panel"),
  selectedDeviceName: document.querySelector("#selected-device-name"),
  revokeDeviceButton: document.querySelector("#revoke-device-button"),
  statusReceived: document.querySelector("#status-received"),
  runStateDot: document.querySelector("#run-state-dot"),
  runStateLabel: document.querySelector("#run-state-label"),
  macroStateLabel: document.querySelector("#macro-state-label"),
  noStatus: document.querySelector("#no-status"),
  statusGrid: document.querySelector("#status-grid"),
  statusError: document.querySelector("#status-error"),
  controlsHelp: document.querySelector("#controls-help"),
  controlsList: document.querySelector("#controls-list"),
  controlsError: document.querySelector("#controls-error"),
  logsPanel: document.querySelector("#logs-panel"),
  logsError: document.querySelector("#logs-error"),
  twoFactorStatus: document.querySelector("#two-factor-status"),
  securityHelp: document.querySelector("#security-help"),
  securityOffPanel: document.querySelector("#security-off-panel"),
  enableTwoFactorButton: document.querySelector("#enable-two-factor-button"),
  enablePasswordForm: document.querySelector("#enable-password-form"),
  enablePasswordInput: document.querySelector("#enable-password-input"),
  enablePasswordSubmit: document.querySelector("#enable-password-submit"),
  securityOnPanel: document.querySelector("#security-on-panel"),
  disableTwoFactorButton: document.querySelector("#disable-two-factor-button"),
  disablePasswordForm: document.querySelector("#disable-password-form"),
  disablePasswordInput: document.querySelector("#disable-password-input"),
  disablePasswordSubmit: document.querySelector("#disable-password-submit"),
  twoFactorSetup: document.querySelector("#two-factor-setup"),
  twoFactorAccount: document.querySelector("#two-factor-account"),
  twoFactorSecret: document.querySelector("#two-factor-secret"),
  twoFactorUri: document.querySelector("#two-factor-uri"),
  copyTwoFactorSecret: document.querySelector("#copy-two-factor-secret"),
  copyTwoFactorUri: document.querySelector("#copy-two-factor-uri"),
  backupCodeList: document.querySelector("#backup-code-list"),
  verifySetupForm: document.querySelector("#verify-setup-form"),
  setupTotpInput: document.querySelector("#setup-totp-input"),
  verifySetupButton: document.querySelector("#verify-setup-button"),
  securityMessage: document.querySelector("#security-message"),
  refreshAuditButton: document.querySelector("#refresh-audit-button"),
  auditList: document.querySelector("#audit-list"),
  emptyAudit: document.querySelector("#empty-audit"),
  auditError: document.querySelector("#audit-error")
};

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

class SessionExpiredError extends ApiError {
  constructor() {
    super("Your session has expired.", 401);
    this.name = "SessionExpiredError";
  }
}

function isApiPath(path) {
  return path.startsWith("/api/");
}

function getPayloadMessage(payload, fallback) {
  return payload?.message || payload?.error || payload?.data?.message || fallback;
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (options.body !== undefined) headers.set("Content-Type", "application/json");

  // Every request is bounded by a timeout so a hung/unreachable backend can never leave the UI stuck
  // (the initial GET /api/me on the loading screen, or a button disabled forever waiting on a POST).
  // Safe (idempotent) requests use a short timeout and a plain "did not respond" message. Mutating
  // requests use a generous timeout AND, on timeout, a NEUTRAL message: the action may already have
  // been applied server-side, so we must not imply a clean failure that invites a double-executing
  // retry -- we tell the user to reload and check first.
  const method = (options.method || "GET").toUpperCase();
  const isSafe = method === "GET" || method === "HEAD";
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? (isSafe ? 15000 : 30000);
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(path, { ...options, credentials: "same-origin", headers, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(
        isSafe
          ? "The server did not respond in time. Is the backend running?"
          : "The request timed out and may or may not have completed. Reload the page to check its state before trying again.",
        0,
      );
    }
    throw new ApiError("Could not reach the server. Is the backend running?", 0);
  } finally {
    window.clearTimeout(timer);
  }
  let payload = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
  }

  // A 401 from a NON-auth API call means the session expired; bounce to login. A 401 from an auth
  // endpoint is a failed sign-in/sign-up and must surface its message to the user instead.
  if (response.status === 401 && isApiPath(path) && !path.startsWith("/api/auth/")) {
    showLogin();
    throw new SessionExpiredError();
  }
  if (!response.ok) {
    throw new ApiError(getPayloadMessage(payload, `Request failed (${response.status}).`), response.status);
  }
  return payload;
}

function jsonBody(value) {
  return JSON.stringify(value);
}

function setView(view) {
  state.view = view;
  elements.loadingView.hidden = view !== "loading";
  elements.loginView.hidden = view !== "login";
  elements.twoFactorView.hidden = view !== "two-factor";
  elements.dashboardView.hidden = view !== "dashboard";
  // Tell the index.html watchdog the app started so it stops showing the loading fallback.
  if (view !== "loading") window.__APP_READY__ = true;
}

function showLogin(message = "") {
  stopAllPolling();
  state.user = null;
  state.devices = [];
  state.selectedId = null;
  state.commands = null;
  state.status = null;
  state.pairCode = null;
  state.securitySetup = null;
  state.audit = [];
  state.auditError = "";
  setTwoFactorMode("totp");
  clearMessage(elements.twoFactorError);
  clearMessage(elements.securityMessage);
  elements.authError.textContent = message;
  elements.authError.hidden = !message;
  elements.pairPanel.hidden = true;
  elements.devicePanel.hidden = true;
  setView("login");
}

function showDashboard() {
  setView("dashboard");
  elements.userEmail.textContent = state.user?.email || "";
  elements.authError.hidden = true;
  renderSecurity();
  startDevicePolling();
}

function showTwoFactorChallenge() {
  setTwoFactorMode("totp");
  clearMessage(elements.twoFactorError);
  elements.twoFactorCodeInput.value = "";
  setView("two-factor");
  window.setTimeout(() => elements.twoFactorCodeInput.focus(), 0);
}

function showMessage(element, message, type = "error") {
  element.textContent = message;
  element.classList.toggle("success-message", type === "success");
  element.classList.toggle("error-message", type === "error");
  element.classList.toggle("info-message", type === "info");
  element.hidden = !message;
}

function clearMessage(element) {
  showMessage(element, "");
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function formatRelative(value) {
  if (!value) return "Never seen";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function setTwoFactorMode(mode) {
  state.twoFactorMode = mode;
  const isBackup = mode === "backup";
  elements.twoFactorCodeLabel.textContent = isBackup ? "Backup code" : "Authentication code";
  elements.twoFactorCodeInput.value = "";
  elements.twoFactorCodeInput.inputMode = isBackup ? "text" : "numeric";
  elements.twoFactorCodeInput.autocomplete = isBackup ? "off" : "one-time-code";
  if (isBackup) {
    elements.twoFactorCodeInput.removeAttribute("pattern");
    elements.twoFactorCodeInput.maxLength = 128;
    elements.backupCodeToggle.textContent = "Use an authenticator code instead";
  } else {
    elements.twoFactorCodeInput.setAttribute("pattern", "[0-9]{6}");
    elements.twoFactorCodeInput.maxLength = 6;
    elements.backupCodeToggle.textContent = "Use a backup code instead";
  }
}

function renderSecurity() {
  const enabled = Boolean(state.user?.twoFactorEnabled);
  const hasSetup = Boolean(state.securitySetup);
  elements.twoFactorStatus.textContent = `Two-factor authentication: ${enabled ? "On" : "Off"}`;
  elements.twoFactorStatus.classList.toggle("on", enabled);
  elements.twoFactorStatus.classList.toggle("off", !enabled);
  elements.securityHelp.textContent = enabled
    ? "Two-factor authentication is protecting your account."
    : "Use an authenticator app to protect your account.";
  elements.securityOffPanel.hidden = enabled || hasSetup;
  elements.securityOnPanel.hidden = !enabled || hasSetup;
  elements.twoFactorSetup.hidden = !hasSetup;

  if (enabled || hasSetup) {
    elements.enablePasswordForm.hidden = true;
    elements.enableTwoFactorButton.hidden = true;
  } else {
    elements.enablePasswordForm.hidden = true;
    elements.enableTwoFactorButton.hidden = false;
  }
  if (enabled && !hasSetup) {
    elements.disablePasswordForm.hidden = true;
    elements.disableTwoFactorButton.hidden = false;
  } else {
    elements.disablePasswordForm.hidden = true;
    elements.disableTwoFactorButton.hidden = false;
  }

  if (!hasSetup) return;
  elements.twoFactorAccount.textContent = state.user?.email || "Account";
  elements.twoFactorSecret.textContent = state.securitySetup.secret || "Secret unavailable";
  elements.twoFactorUri.textContent = state.securitySetup.totpURI || "URI unavailable";
  elements.backupCodeList.replaceChildren();
  for (const code of state.securitySetup.backupCodes) {
    const item = document.createElement("li");
    item.textContent = code;
    elements.backupCodeList.append(item);
  }
}

function getTotpSecret(totpURI) {
  try {
    return new URL(totpURI).searchParams.get("secret") || "";
  } catch {
    const match = String(totpURI).match(/[?&]secret=([^&]+)/i);
    return match ? decodeURIComponent(match[1]) : "";
  }
}

function renderAudit() {
  elements.auditList.replaceChildren();
  const entries = Array.isArray(state.audit) ? state.audit : [];
  elements.emptyAudit.hidden = entries.length !== 0;
  for (const entry of entries) {
    const item = document.createElement("article");
    item.className = "audit-entry";

    const heading = document.createElement("div");
    heading.className = "audit-entry-heading";
    const action = document.createElement("strong");
    action.textContent = entry.action || "Unknown action";
    const time = document.createElement("time");
    time.dateTime = entry.createdAt || "";
    time.textContent = formatRelative(entry.createdAt);
    time.title = formatDate(entry.createdAt);
    heading.append(action, time);

    const detail = document.createElement("p");
    detail.className = "audit-detail";
    detail.textContent = entry.detail || "No detail provided.";
    item.append(heading, detail);

    const metadata = [];
    if (entry.deviceId) metadata.push(`Device: ${entry.deviceId}`);
    if (entry.ip) metadata.push(`IP: ${entry.ip}`);
    if (metadata.length) {
      const meta = document.createElement("p");
      meta.className = "audit-metadata";
      meta.textContent = metadata.join(" | ");
      item.append(meta);
    }
    elements.auditList.append(item);
  }
  clearMessage(elements.auditError);
  if (state.auditError) showMessage(elements.auditError, state.auditError);
}

async function refreshAudit() {
  if (state.view !== "dashboard") return;
  elements.refreshAuditButton.disabled = true;
  try {
    state.audit = (await api("/api/audit?limit=100")) || [];
    state.auditError = "";
    renderAudit();
  } catch (error) {
    if (!(error instanceof SessionExpiredError)) {
      state.auditError = error.message;
      renderAudit();
    }
  } finally {
    elements.refreshAuditButton.disabled = false;
  }
}

function formatTime(value) {
  if (!value) return "--:--:--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "--:--:--" : date.toLocaleTimeString();
}

function setStatusDot(dot, online) {
  dot.classList.toggle("online", Boolean(online));
  dot.classList.toggle("offline", !online);
}

function makeStatus(isOnline, label) {
  const wrapper = document.createElement("span");
  wrapper.className = "status-label";
  const dot = document.createElement("span");
  dot.className = "status-dot";
  setStatusDot(dot, isOnline);
  dot.setAttribute("aria-hidden", "true");
  const text = document.createElement("span");
  text.textContent = label;
  wrapper.append(dot, text);
  return wrapper;
}

function selectedDevice() {
  return state.devices.find((device) => device.id === state.selectedId) || null;
}

function renderDevices() {
  elements.deviceList.replaceChildren();
  const devices = state.devices;
  elements.emptyDevices.hidden = devices.length !== 0;
  for (const device of devices) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "device-row";
    row.classList.toggle("selected", device.id === state.selectedId);
    row.classList.toggle("revoked", Boolean(device.revokedAt));
    row.addEventListener("click", () => selectDevice(device.id));

    const identity = document.createElement("span");
    identity.className = "device-identity";
    const name = document.createElement("strong");
    name.textContent = device.name || "Unnamed device";
    identity.append(name);
    if (device.revokedAt) {
      const revoked = document.createElement("span");
      revoked.className = "tag revoked-tag";
      revoked.textContent = "revoked";
      identity.append(revoked);
    }

    const signals = document.createElement("span");
    signals.className = "device-signals";
    signals.append(makeStatus(device.agentOnline, device.agentOnline ? "Agent online" : "Agent offline"));
    signals.append(makeStatus(device.macroOnline, device.macroOnline ? "Macro online" : "Macro offline"));

    const lastSeen = document.createElement("span");
    lastSeen.className = "last-seen";
    lastSeen.textContent = formatRelative(device.lastSeenAt);
    lastSeen.title = device.lastSeenAt ? formatDate(device.lastSeenAt) : "No last-seen timestamp";

    row.append(identity, signals, lastSeen);
    elements.deviceList.append(row);
  }
}

async function refreshDevices() {
  if (state.view !== "dashboard") return;
  try {
    state.devices = (await api("/api/devices")) || [];
    clearMessage(elements.devicesError);
    renderDevices();
    const current = selectedDevice();
    if (state.selectedId && (!current || current.revokedAt)) clearSelection();
    else if (current) renderSelectedDeviceHeading();
  } catch (error) {
    if (!(error instanceof SessionExpiredError)) showMessage(elements.devicesError, error.message);
  }
}

function startDevicePolling() {
  if (state.deviceTimer) return;
  void refreshDevices();
  state.deviceTimer = window.setInterval(() => void refreshDevices(), 5000);
}

function stopAllPolling() {
  if (state.deviceTimer) window.clearInterval(state.deviceTimer);
  state.deviceTimer = null;
  stopSelectedPolling();
}

function stopSelectedPolling() {
  // status/logs poll via self-scheduling setTimeout loops (see statusLoop/logsLoop), so cancel with
  // clearTimeout. Bumping the selection token also stops any in-flight loop from rescheduling.
  if (state.statusTimer) window.clearTimeout(state.statusTimer);
  if (state.logsTimer) window.clearTimeout(state.logsTimer);
  state.statusTimer = null;
  state.logsTimer = null;
  state.selectionToken += 1;
}

// Poll on a self-scheduling loop that AWAITS each request before scheduling the next, so slow
// requests can never overlap (which would duplicate logs or rewind the cursor).
async function statusLoop(token) {
  if (!isCurrentSelection(token)) return;
  await pollStatus(token);
  if (!isCurrentSelection(token)) return;
  state.statusTimer = window.setTimeout(() => void statusLoop(token), 2000);
}

async function logsLoop(token) {
  if (!isCurrentSelection(token)) return;
  await pollLogs(token);
  if (!isCurrentSelection(token)) return;
  state.logsTimer = window.setTimeout(() => void logsLoop(token), 2000);
}

function renderSelectedDeviceHeading() {
  const device = selectedDevice();
  if (device) elements.selectedDeviceName.textContent = device.name || "Unnamed device";
}

function clearSelection() {
  stopSelectedPolling();
  state.selectedId = null;
  state.status = null;
  state.logs = [];
  state.lastLogId = 0;
  state.commandInFlight = false;
  elements.devicePanel.hidden = true;
  elements.logsPanel.replaceChildren();
  renderDevices();
}

function selectDevice(id) {
  const device = state.devices.find((candidate) => candidate.id === id);
  if (!device || device.revokedAt) return;
  stopSelectedPolling();
  state.selectedId = id;
  state.status = null;
  state.statusError = "";
  state.logs = [];
  state.lastLogId = 0;
  state.commandInFlight = false;
  elements.devicePanel.hidden = false;
  elements.logsPanel.replaceChildren();
  renderDevices();
  renderSelectedDeviceHeading();
  renderStatus();
  renderControls();
  const token = state.selectionToken;
  void statusLoop(token);
  void logsLoop(token);
}

function isCurrentSelection(token) {
  return token === state.selectionToken && Boolean(selectedDevice());
}

async function pollStatus(token = state.selectionToken) {
  const device = selectedDevice();
  if (!device || !isCurrentSelection(token)) return;
  try {
    const snapshot = await api(`/api/devices/${encodeURIComponent(device.id)}/status`);
    if (!isCurrentSelection(token)) return;
    state.status = snapshot;
    state.statusError = "";
    renderStatus();
    renderControls();
  } catch (error) {
    if (!isCurrentSelection(token)) return;
    if (!(error instanceof SessionExpiredError)) {
      state.statusError = error.message;
      renderStatus();
    }
  }
}

function getRunState(snapshot) {
  if (snapshot?.state === "running" || snapshot?.state === "paused" || snapshot?.state === "stopped") {
    return snapshot.state;
  }
  if (snapshot?.paused) return "paused";
  if (snapshot?.running) return "running";
  return "stopped";
}

function renderStatus() {
  const snapshot = state.status;
  const device = selectedDevice();
  const hasStatus = snapshot !== null;
  elements.noStatus.hidden = hasStatus;
  elements.statusGrid.hidden = !hasStatus;
  clearMessage(elements.statusError);
  if (state.statusError) showMessage(elements.statusError, state.statusError);

  const macroOnline = Boolean(snapshot?.macroOnline ?? device?.macroOnline);
  const runState = hasStatus ? getRunState(snapshot) : "stopped";
  setStatusDot(elements.runStateDot, macroOnline);
  elements.runStateDot.classList.toggle("running", runState === "running" && macroOnline);
  elements.runStateDot.classList.toggle("paused", runState === "paused" && macroOnline);
  elements.runStateLabel.textContent = hasStatus ? runState : "No status";
  elements.runStateLabel.className = `run-state-${hasStatus ? runState : "none"}`;
  elements.macroStateLabel.textContent = macroOnline ? "Macro online" : "Macro offline";
  elements.statusReceived.textContent = snapshot?.receivedAt ? `Updated ${formatRelative(snapshot.receivedAt)}` : "";

  const values = {
    activePreset: snapshot?.activePreset,
    runningPreset: snapshot?.runningPreset,
    queuedPreset: snapshot?.queuedPreset,
    currentMap: snapshot?.currentMap,
    currentScreen: snapshot?.currentScreen,
    currentStep: snapshot?.currentStep,
    cycleCount: snapshot?.cycleCount,
    stepRepeatCount: snapshot?.stepRepeatCount,
    startRepeatCount: snapshot?.startRepeatCount,
    victoryCount: snapshot?.victoryCount,
    defeatCount: snapshot?.defeatCount,
    dryRun: snapshot?.dryRun === undefined ? undefined : snapshot.dryRun ? "Yes" : "No"
  };
  for (const field of elements.statusGrid.querySelectorAll("[data-status-field]")) {
    const value = values[field.dataset.statusField];
    field.textContent = value === undefined || value === null || value === "" ? "-" : String(value);
  }
}

function renderControls() {
  elements.controlsList.replaceChildren();
  clearMessage(elements.controlsError);
  const meta = state.commands?.meta || {};
  const types = state.commands?.types || Object.keys(meta);
  if (!types.length) {
    elements.controlsHelp.textContent = "No commands are available.";
    return;
  }
  const online = Boolean(state.status?.macroOnline ?? selectedDevice()?.macroOnline);
  elements.controlsHelp.textContent = online ? "Choose an action to send to the macro." : "Controls are disabled while the macro is offline.";
  for (const type of types) {
    const commandMeta = meta[type] || {};
    const row = document.createElement("div");
    row.className = "control-row";
    const description = document.createElement("div");
    description.className = "control-description";
    const label = document.createElement("strong");
    label.textContent = commandMeta.label || type;
    description.append(label);
    if (commandMeta.description) {
      const detail = document.createElement("small");
      detail.textContent = commandMeta.description;
      description.append(detail);
    }
    const action = document.createElement("div");
    action.className = "control-action";
    let input = null;
    if (commandMeta.usesArg) {
      input = document.createElement("input");
      input.type = "text";
      input.className = "command-arg";
      input.placeholder = commandMeta.argLabel || "Argument";
      input.setAttribute("aria-label", `${commandMeta.argLabel || "Argument"} for ${commandMeta.label || type}`);
      action.append(input);
    }
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary-button command-button";
    button.textContent = commandMeta.label || type;
    button.addEventListener("click", () => void sendCommand(type, input?.value));
    action.append(button);
    row.append(description, action);
    elements.controlsList.append(row);
  }
  updateControlsDisabled();
}

function updateControlsDisabled() {
  const online = Boolean(state.status?.macroOnline ?? selectedDevice()?.macroOnline);
  for (const control of elements.controlsList.querySelectorAll("button, input")) {
    control.disabled = state.commandInFlight || !online;
  }
}

function showCommandNotice(message, type) {
  clearTimeout(state.noticeTimer);
  const notice = document.createElement("p");
  notice.className = `command-notice ${type}`;
  notice.setAttribute("role", "status");
  notice.textContent = message;
  elements.controlsList.append(notice);
  state.noticeTimer = window.setTimeout(() => notice.remove(), 5000);
}

function sleep(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

async function sendCommand(type, arg) {
  const device = selectedDevice();
  if (!device || state.commandInFlight) return;
  const commandSelectionToken = state.selectionToken;
  const online = Boolean(state.status?.macroOnline ?? device.macroOnline);
  if (!online) return;
  state.commandInFlight = true;
  updateControlsDisabled();
  try {
    const body = { type };
    if (arg !== undefined && arg.trim() !== "") body.arg = arg.trim();
    const result = await api(`/api/devices/${encodeURIComponent(device.id)}/commands`, {
      method: "POST",
      body: jsonBody(body)
    });
    let command = null;
    for (let attempt = 0; attempt < 10; attempt += 1) {
      await sleep(500);
      command = await api(`/api/devices/${encodeURIComponent(device.id)}/commands/${encodeURIComponent(result.commandId)}`);
      if (["acked", "error", "expired"].includes(command?.status)) break;
    }
    if (!isCurrentSelection(commandSelectionToken)) return;
    if (command?.status === "acked") {
      showCommandNotice(command.message || "Command acknowledged.", command.ok === false ? "error" : "success");
    } else if (command?.status === "error" || command?.status === "expired") {
      showCommandNotice(command.message || `Command ${command.status}.`, "error");
    } else {
      showCommandNotice("Command is still pending.", "info");
    }
  } catch (error) {
    if (!(error instanceof SessionExpiredError)) showCommandNotice(error.message, "error");
  } finally {
    // Only clear the in-flight flag if we are still on the selection that issued the command, so a
    // command resolving after the user switched devices cannot re-enable controls for a newer one.
    if (isCurrentSelection(commandSelectionToken)) {
      state.commandInFlight = false;
      updateControlsDisabled();
    }
  }
}

async function pollLogs(token = state.selectionToken) {
  const device = selectedDevice();
  if (!device || !isCurrentSelection(token)) return;
  try {
    const query = `?since=${encodeURIComponent(String(state.lastLogId))}&limit=1000`;
    const result = await api(`/api/devices/${encodeURIComponent(device.id)}/logs${query}`);
    if (!isCurrentSelection(token)) return;
    clearMessage(elements.logsError);
    appendLogs(result?.lines || []);
    // Only ever advance the cursor, so a late/out-of-order response can never rewind it.
    if (typeof result?.lastId === "number") state.lastLogId = Math.max(state.lastLogId, result.lastId);
  } catch (error) {
    if (isCurrentSelection(token) && !(error instanceof SessionExpiredError)) {
      state.logsError = error.message;
      showMessage(elements.logsError, state.logsError);
    }
  }
}

function appendLogs(lines) {
  if (!lines.length) return;
  const shouldStickToBottom = elements.logsPanel.scrollHeight - elements.logsPanel.scrollTop - elements.logsPanel.clientHeight < 24;
  for (const log of lines) {
    const line = document.createElement("div");
    line.className = "log-line";
    const time = document.createElement("span");
    time.className = "log-time";
    time.textContent = formatTime(log.at);
    const text = document.createElement("span");
    text.className = "log-text";
    text.textContent = log.line ?? "";
    line.append(time, text);
    elements.logsPanel.append(line);
    state.logs.push(log);
  }
  while (state.logs.length > 1000) state.logs.shift();
  while (elements.logsPanel.children.length > 1000) elements.logsPanel.firstElementChild.remove();
  if (shouldStickToBottom) elements.logsPanel.scrollTop = elements.logsPanel.scrollHeight;
}

async function loadCommands() {
  try {
    state.commands = await api("/api/commands");
    if (state.selectedId) renderControls();
  } catch (error) {
    if (!(error instanceof SessionExpiredError)) showMessage(elements.controlsError, error.message);
  }
}

async function refreshUser() {
  state.user = await api("/api/me");
  elements.userEmail.textContent = state.user?.email || "";
  renderSecurity();
}

async function handleTwoFactorSubmit(event) {
  event.preventDefault();
  clearMessage(elements.twoFactorError);
  if (!elements.twoFactorForm.reportValidity()) return;
  const isBackup = state.twoFactorMode === "backup";
  const path = isBackup ? "/api/auth/two-factor/verify-backup-code" : "/api/auth/two-factor/verify-totp";
  elements.twoFactorSubmit.disabled = true;
  elements.twoFactorSubmit.textContent = "Verifying...";
  try {
    await api(path, {
      method: "POST",
      body: jsonBody({ code: elements.twoFactorCodeInput.value.trim() })
    });
    await refreshUser();
    showDashboard();
    await Promise.all([loadCommands(), refreshDevices(), refreshAudit()]);
  } catch (error) {
    if (!(error instanceof SessionExpiredError)) showMessage(elements.twoFactorError, error.message);
  } finally {
    elements.twoFactorSubmit.disabled = false;
    elements.twoFactorSubmit.textContent = "Verify";
  }
}

function beginEnableTwoFactor() {
  elements.enableTwoFactorButton.hidden = true;
  elements.enablePasswordForm.hidden = false;
  elements.enablePasswordInput.focus();
}

async function enableTwoFactor(event) {
  event.preventDefault();
  clearMessage(elements.securityMessage);
  if (!elements.enablePasswordForm.reportValidity()) return;
  elements.enablePasswordSubmit.disabled = true;
  elements.enablePasswordSubmit.textContent = "Preparing...";
  try {
    const result = await api("/api/auth/two-factor/enable", {
      method: "POST",
      body: jsonBody({ password: elements.enablePasswordInput.value })
    });
    const totpURI = String(result?.totpURI || "");
    state.securitySetup = {
      totpURI,
      secret: getTotpSecret(totpURI),
      backupCodes: Array.isArray(result?.backupCodes) ? result.backupCodes : []
    };
    elements.enablePasswordInput.value = "";
    renderSecurity();
    showMessage(elements.securityMessage, "Setup details generated. Verify a code to activate two-factor authentication.", "info");
    elements.setupTotpInput.focus();
  } catch (error) {
    if (!(error instanceof SessionExpiredError)) showMessage(elements.securityMessage, error.message);
  } finally {
    elements.enablePasswordSubmit.disabled = false;
    elements.enablePasswordSubmit.textContent = "Continue";
  }
}

function beginDisableTwoFactor() {
  elements.disableTwoFactorButton.hidden = true;
  elements.disablePasswordForm.hidden = false;
  elements.disablePasswordInput.focus();
}

async function disableTwoFactor(event) {
  event.preventDefault();
  clearMessage(elements.securityMessage);
  if (!elements.disablePasswordForm.reportValidity()) return;
  elements.disablePasswordSubmit.disabled = true;
  elements.disablePasswordSubmit.textContent = "Disabling...";
  try {
    await api("/api/auth/two-factor/disable", {
      method: "POST",
      body: jsonBody({ password: elements.disablePasswordInput.value })
    });
    await refreshUser();
    elements.disablePasswordInput.value = "";
    showMessage(elements.securityMessage, "Two-factor authentication has been disabled.", "success");
  } catch (error) {
    if (!(error instanceof SessionExpiredError)) showMessage(elements.securityMessage, error.message);
  } finally {
    elements.disablePasswordSubmit.disabled = false;
    elements.disablePasswordSubmit.textContent = "Disable";
  }
}

async function verifyTwoFactorSetup(event) {
  event.preventDefault();
  clearMessage(elements.securityMessage);
  if (!elements.verifySetupForm.reportValidity()) return;
  elements.verifySetupButton.disabled = true;
  elements.verifySetupButton.textContent = "Verifying...";
  try {
    await api("/api/auth/two-factor/verify-totp", {
      method: "POST",
      body: jsonBody({ code: elements.setupTotpInput.value.trim() })
    });
    await refreshUser();
    state.securitySetup = null;
    elements.setupTotpInput.value = "";
    renderSecurity();
    showMessage(elements.securityMessage, "Two-factor authentication is now active.", "success");
  } catch (error) {
    if (!(error instanceof SessionExpiredError)) showMessage(elements.securityMessage, error.message);
  } finally {
    elements.verifySetupButton.disabled = false;
    elements.verifySetupButton.textContent = "Verify and activate";
  }
}

async function copyText(value, messageElement, successMessage) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
    } else {
      const helper = document.createElement("textarea");
      helper.value = value;
      helper.setAttribute("readonly", "true");
      helper.className = "clipboard-helper";
      document.body.append(helper);
      helper.select();
      document.execCommand("copy");
      helper.remove();
    }
    showMessage(messageElement, successMessage, "success");
  } catch {
    showMessage(messageElement, "Copy failed. Select the value and copy it manually.", "error");
  }
}

function copyTwoFactorSecret() {
  const secret = state.securitySetup?.secret;
  if (secret) void copyText(secret, elements.securityMessage, "Secret copied.");
}

function copyTwoFactorUri() {
  const uri = state.securitySetup?.totpURI;
  if (uri) void copyText(uri, elements.securityMessage, "Authenticator URI copied.");
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  clearMessage(elements.authError);
  if (!elements.authForm.reportValidity()) return;
  const isSignUp = state.loginMode === "signup";
  const body = {
    email: elements.emailInput.value.trim(),
    password: elements.passwordInput.value
  };
  if (isSignUp) body.name = elements.nameInput.value.trim();
  elements.authSubmit.disabled = true;
  elements.authSubmit.textContent = isSignUp ? "Creating account..." : "Signing in...";
  try {
    const result = await api(isSignUp ? "/api/auth/sign-up/email" : "/api/auth/sign-in/email", {
      method: "POST",
      body: jsonBody(body)
    });
    if (!isSignUp && result?.twoFactorRedirect === true) {
      showTwoFactorChallenge();
      return;
    }
    await refreshUser();
    showDashboard();
    await Promise.all([loadCommands(), refreshDevices(), refreshAudit()]);
  } catch (error) {
    if (!(error instanceof SessionExpiredError)) showMessage(elements.authError, error.message);
  } finally {
    elements.authSubmit.disabled = false;
    elements.authSubmit.textContent = isSignUp ? "Create account" : "Sign in";
  }
}

function setLoginMode(mode) {
  state.loginMode = mode;
  const isSignUp = mode === "signup";
  elements.nameField.hidden = !isSignUp;
  elements.nameInput.required = isSignUp;
  elements.passwordInput.minLength = isSignUp ? 10 : 0;
  elements.passwordInput.autocomplete = isSignUp ? "new-password" : "current-password";
  elements.authSubmit.textContent = isSignUp ? "Create account" : "Sign in";
  elements.signInMode.classList.toggle("active", !isSignUp);
  elements.signUpMode.classList.toggle("active", isSignUp);
  elements.signInMode.setAttribute("aria-selected", String(!isSignUp));
  elements.signUpMode.setAttribute("aria-selected", String(isSignUp));
  clearMessage(elements.authError);
}

async function addDevice() {
  elements.addDeviceButton.disabled = true;
  clearMessage(elements.pairMessage);
  try {
    const deviceName = elements.deviceNameInput.value;
    const body = deviceName.trim() ? { deviceName: deviceName.trim() } : {};
    state.pairCode = await api("/api/devices/pair-code", { method: "POST", body: jsonBody(body) });
    elements.pairCode.textContent = state.pairCode.code || "-";
    elements.pairExpiry.textContent = `Expires ${formatDate(state.pairCode.expiresAt)}`;
    elements.pairCommand.textContent = `agent --server ${window.location.origin} --pair ${state.pairCode.code || ""}`;
    elements.pairPanel.hidden = false;
    elements.deviceNameInput.value = "";
  } catch (error) {
    if (!(error instanceof SessionExpiredError)) showMessage(elements.pairMessage, error.message);
  } finally {
    elements.addDeviceButton.disabled = false;
  }
}

async function copyPairCode() {
  const code = state.pairCode?.code;
  if (!code) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(code);
    } else {
      const helper = document.createElement("textarea");
      helper.value = code;
      helper.setAttribute("readonly", "true");
      helper.className = "clipboard-helper";
      document.body.append(helper);
      helper.select();
      document.execCommand("copy");
      helper.remove();
    }
    showMessage(elements.pairMessage, "Pairing code copied.", "success");
  } catch {
    showMessage(elements.pairMessage, "Copy failed. Select the code and copy it manually.", "error");
  }
}

async function signOut() {
  elements.signOutButton.disabled = true;
  try {
    await api("/api/auth/sign-out", { method: "POST" });
  } catch (error) {
    if (!(error instanceof SessionExpiredError)) showLogin(error.message);
  } finally {
    showLogin();
    elements.signOutButton.disabled = false;
  }
}

async function revokeSelectedDevice() {
  const device = selectedDevice();
  if (!device || !window.confirm(`Revoke ${device.name || "this device"}?`)) return;
  elements.revokeDeviceButton.disabled = true;
  try {
    await api(`/api/devices/${encodeURIComponent(device.id)}/revoke`, { method: "POST" });
    clearSelection();
    await refreshDevices();
  } catch (error) {
    if (!(error instanceof SessionExpiredError)) showMessage(elements.statusError, error.message);
  } finally {
    elements.revokeDeviceButton.disabled = false;
  }
}

elements.authForm.addEventListener("submit", (event) => void handleAuthSubmit(event));
elements.twoFactorForm.addEventListener("submit", (event) => void handleTwoFactorSubmit(event));
elements.backupCodeToggle.addEventListener("click", () => setTwoFactorMode(state.twoFactorMode === "backup" ? "totp" : "backup"));
elements.backToSignIn.addEventListener("click", () => showLogin());
elements.signInMode.addEventListener("click", () => setLoginMode("signin"));
elements.signUpMode.addEventListener("click", () => setLoginMode("signup"));
elements.addDeviceButton.addEventListener("click", () => void addDevice());
elements.copyCodeButton.addEventListener("click", () => void copyPairCode());
elements.signOutButton.addEventListener("click", () => void signOut());
elements.revokeDeviceButton.addEventListener("click", () => void revokeSelectedDevice());
elements.enableTwoFactorButton.addEventListener("click", beginEnableTwoFactor);
elements.enablePasswordForm.addEventListener("submit", (event) => void enableTwoFactor(event));
elements.disableTwoFactorButton.addEventListener("click", beginDisableTwoFactor);
elements.disablePasswordForm.addEventListener("submit", (event) => void disableTwoFactor(event));
elements.verifySetupForm.addEventListener("submit", (event) => void verifyTwoFactorSetup(event));
elements.copyTwoFactorSecret.addEventListener("click", copyTwoFactorSecret);
elements.copyTwoFactorUri.addEventListener("click", copyTwoFactorUri);
elements.refreshAuditButton.addEventListener("click", () => void refreshAudit());

async function bootstrap() {
  try {
    state.user = await api("/api/me");
    showDashboard();
    await Promise.all([loadCommands(), refreshDevices(), refreshAudit()]);
  } catch (error) {
    if (error instanceof SessionExpiredError) return;
    showLogin(error.message || "Unable to load the session.");
  }
}

setLoginMode("signin");
void bootstrap();
