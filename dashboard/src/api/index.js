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
export const login = (email, password) => {
  const form = new URLSearchParams();
  form.append("username", email);
  form.append("password", password);
  return api.post("/auth/login", form);
};
export const getMe = () => api.get("/auth/me");

// Machines
export const getMachines      = ()          => api.get("/machines");
export const getMachine       = (id)        => api.get(`/machines/${id}`);
export const deleteMachine    = (id)        => api.delete(`/machines/${id}`);
export const getMetrics       = (id)        => api.get(`/machines/${id}/metrics`);
export const getLatest        = (id)        => api.get(`/machines/${id}/metrics/latest`);
export const getLogs          = (id)        => api.get(`/machines/${id}/logs`);
export const getAlerts        = (id)        => api.get(`/machines/${id}/alerts`);
export const sendCommand      = (id, type)  => api.post(`/machines/${id}/command`, { type });
export const getCommandStatus = (id, cid)   => api.get(`/machines/${id}/command/${cid}`);

// Reports
export const generateReport = (id)  => api.post(`/reports/${id}`);
export const getReports     = ()    => api.get("/reports");
export const deleteReport   = (id)  => api.delete(`/reports/${id}`);
export const downloadReport = (id)  => `${BASE}/reports/${id}/download`;

// Users
export const getUsers       = ()     => api.get("/auth/users");
export const createUser     = (data) => api.post("/auth/users", data);
export const deactivateUser = (id)   => api.patch(`/auth/users/${id}/deactivate`);

// WebSocket
export const connectDashboardWS = (onMessage) => {
  const ws = new WebSocket("ws://localhost:8000/ws/dashboard");
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  ws.onerror   = (e) => console.error("[WS] error", e);
  ws.onclose   = ()  => console.log("[WS] dashboard disconnected");
  return ws;
};

export default api;
