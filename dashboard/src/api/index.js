import axios from "axios";

const BASE = window.location.origin;

let _token = null;
export const setToken = (t) => { _token = t; };
export const getToken = ()  => _token;

const api = axios.create({ baseURL: BASE });
api.interceptors.request.use((cfg) => {
  if (_token) cfg.headers.Authorization = `Bearer ${_token}`;
  return cfg;
});

// Auth -- backend expects application/x-www-form-urlencoded (OAuth2PasswordRequestForm)
export const login = (email, password) => {
  const body = new URLSearchParams();
  body.append("username", email);
  body.append("password", password);
  return api.post("/api/auth/login", body, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
};
export const getMe = () => api.get("/api/auth/me");
export const changePassword = (current_password, new_password) =>
  api.post("/api/auth/change-password", { current_password, new_password });

// Users
export const getUsers       = ()     => api.get("/api/auth/users");
export const createUser     = (data) => api.post("/api/auth/users", data);
export const deactivateUser = (id)   => api.patch(`/api/auth/users/${id}/deactivate`);

// Machines
export const getMachines      = ()          => api.get("/api/machines");
export const getMachine       = (id)        => api.get(`/api/machines/${id}`);
export const deleteMachine    = (id)        => api.delete(`/api/machines/${id}`);
export const getLogs          = (id)        => api.get(`/api/machines/${id}/logs`);

// Pending enrollment
export const getPendingMachines = ()   => api.get("/api/machines/pending");
export const getInstallCommand  = ()   => api.get("/api/machines/install-command");
export const approveMachine     = (id) => api.post(`/api/machines/${id}/approve`);
export const rejectMachine      = (id) => api.post(`/api/machines/${id}/reject`);

// Metrics
export const getMetrics = (id) => api.get(`/api/machines/${id}/metrics`);
export const getLatest  = (id) => api.get(`/api/machines/${id}/metrics/latest`);
export const getAlerts  = (id) => api.get(`/api/machines/${id}/alerts`);

// Commands
export const sendCommand      = (id, type, params = {}, passphrase = null) =>
  api.post(`/api/machines/${id}/command`, { type, params, passphrase });
export const getCommandStatus = (id, cid)   => api.get(`/api/machines/${id}/command/${cid}`);
export const getSnapshots     = (id)        => api.get(`/api/machines/${id}/snapshots`);
export const setNodePassphrase   = (id, passphrase) => api.post(`/api/machines/${id}/passphrase`, { passphrase });
export const clearNodePassphrase = (id)             => api.delete(`/api/machines/${id}/passphrase`);
export const getPassphraseStatus = (id)             => api.get(`/api/machines/${id}/passphrase-status`);

// Reports
export const generateReport = (id)  => api.post(`/api/reports/${id}`);
export const getReports     = ()    => api.get("/api/reports");
export const deleteReport   = (id)  => api.delete(`/api/reports/${id}`);
export const downloadReport = (id)  => `${BASE}/api/reports/${id}/download`;

// Analytics / Fleet overview
export const getFleetOverview = ()   => api.get("/api/analytics/fleet");
export const getMachineScore  = (id) => api.get(`/api/analytics/machine/${id}/score`);
export const getAllAlerts     = ()   => api.get("/api/analytics/alerts/all");
export const markAllRead      = ()   => api.post("/api/analytics/alerts/mark-all-read");
export const getSavings       = ()   => api.get("/api/analytics/savings");

// Fleet commands
export const fleetCommand = (type, machine_ids = []) =>
  api.post("/api/fleet/command", { type, machine_ids, params: {} });
export const getFleetStatus = () => api.get("/api/fleet/status");

// Audit
export const getAuditLogs   = ()   => api.get("/api/audit/logs");
export const exportAuditCSV = ()   => `${BASE}/api/audit/logs/export`;
export const verifyLog      = (id) => api.get(`/api/audit/logs/verify/${id}`);

// Schedules
export const getSchedules   = ()   => api.get("/api/schedules");
export const createSchedule = (d)  => api.post("/api/schedules", d);
export const deleteSchedule = (id) => api.delete(`/api/schedules/${id}`);

// Notifications / white label settings
export const updateNotifyConfig = (d) => api.post("/api/settings/notifications", d);
export const getNotifyConfig    = ()  => api.get("/api/settings/notifications");
export const testNotification   = (type) => api.post("/api/settings/notifications/test", { type });

// WebSocket
export const connectDashboardWS = (onMessage) => {
  const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${wsProto}//${window.location.host}/ws/dashboard`);
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  ws.onerror   = (e) => console.error("[WS] error", e);
  ws.onclose   = ()  => console.log("[WS] dashboard disconnected");
  return ws;
};

export default api;
