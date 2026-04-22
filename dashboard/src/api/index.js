import axios from "axios";
const BASE = "http://localhost:8000";
let _token = null;
export const setToken = (t) => { _token = t; };
export const getToken = ()  => _token;
const api = axios.create({ baseURL: BASE });
api.interceptors.request.use((cfg) => {
  if (_token) cfg.headers.Authorization = `Bearer ${_token}`;
  return cfg;
});
// Auth
export const login = (email, password) =>
  api.post("/api/auth/login", { username: email, password });
export const getMe = () => api.get("/api/auth/me");
// Machines
export const getMachines      = ()          => api.get("/api/nodes");
export const getMachine       = (id)        => api.get(`/api/nodes/${id}`);
export const deleteMachine    = (id)        => api.delete(`/api/nodes/${id}`);
export const getMetrics       = (id)        => api.get(`/api/nodes/${id}/metrics/history`);
export const getLatest        = (id)        => api.get(`/api/nodes/${id}/metrics/history`);
export const getLogs          = (id)        => api.get(`/api/audit`);
export const getAlerts        = (id)        => api.get(`/api/alerts`);
export const sendCommand      = (id, type)  => api.post(`/api/nodes/${id}/command`, { command: type, node_ids: [] });
export const getCommandStatus = (id, cid)   => api.get(`/api/nodes/${id}`);
// Reports
export const generateReport = (id)  => api.post(`/api/nodes/${id}/scan`);
export const getReports     = ()    => api.get("/api/audit");
export const deleteReport   = (id)  => api.delete(`/api/nodes/${id}`);
export const downloadReport = (id)  => `${BASE}/analytics/audit`;
// Users
export const getUsers       = ()     => api.get("/api/auth/me");
export const createUser     = (data) => api.post("/api/auth/users", data);
export const deactivateUser = (id)   => api.get("/api/auth/me");
// WebSocket
export const connectDashboardWS = (onMessage) => {
  const ws = new WebSocket("ws://localhost:8000/ws/dashboard");
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  ws.onerror   = (e) => console.error("[WS] error", e);
  ws.onclose   = ()  => console.log("[WS] dashboard disconnected");
  return ws;
};
export default api;
// Analytics
export const getFleetOverview = ()   => api.get("/api/fleet/stats");
export const getMachineScore  = (id) => api.get(`/api/nodes/${id}`);
export const getAllAlerts      = ()   => api.get("/api/alerts");
export const markAllRead       = ()   => api.post("/api/alerts/mark-all-read");
export const getSavings        = ()   => api.get("/api/fleet/stats");
// Fleet commands
export const fleetCommand = (type, machine_ids=[]) =>
  api.post("/api/fleet/command", { command: type, node_ids: machine_ids });
// Audit
export const getAuditLogs   = ()     => api.get("/api/audit");
export const exportAuditCSV = ()     => `${BASE}/analytics/audit`;
export const verifyLog      = (id)   => api.get("/api/audit");
// Schedules
export const getSchedules    = ()    => api.get("/api/fleet/stats");
export const createSchedule  = (d)   => api.post("/api/fleet/command", d);
export const deleteSchedule  = (id)  => api.delete(`/api/nodes/${id}`);
// Notifications config
export const updateNotifyConfig = (d) => api.put("/api/brand", d);
