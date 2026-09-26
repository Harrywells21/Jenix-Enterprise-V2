import axios from "axios";

// Master authenticates via an httponly session cookie (POST /login), not a
// bearer token like Floor 1's dashboard — same-origin requests carry the
// cookie automatically, so no Authorization header is needed here.
const api = axios.create({ baseURL: window.location.origin, withCredentials: true });

export const getFleetOverview = () => api.get("/api/analytics/fleet");
export const getAllAlerts     = () => api.get("/api/analytics/alerts/all");
// Fleet-wide compliance score (real route: master_server.py's
// /api/analytics/fleet/compliance-score, weighted-avg aggregation across
// floors of each floor's real /analytics/fleet/compliance-score). Real
// fields confirmed via live response: score, cve_severity_counts,
// unresolved_alerts, floors[] (per-floor score/grade/color/breakdown),
// floor_errors[]. Nothing beyond these is real.
export const getComplianceScore = () => api.get("/api/analytics/fleet/compliance-score");
export const setAlertStatus   = (floorIdx, alertId, status) =>
  api.patch(`/api/floors/${floorIdx}/alerts/${alertId}/status`, { status });
export const assignAlertToMe  = (floorIdx, alertId) =>
  api.patch(`/api/floors/${floorIdx}/alerts/${alertId}/assign`, {});
export const dispatchCommand  = (floorIdx, machineId, type, params = {}) =>
  api.post(`/api/floors/${floorIdx}/machines/${machineId}/command`, { type, params });

// --- Schedules (real routes: server/routes/schedules.py, proxied via
// master_server.py's /api/analytics/schedules aggregate + /api/floors/{idx}/schedules) ---
// Real ScheduleCreate fields: machine_id, scan_type ("security"/"health"/"full"),
// frequency ("daily"/"weekly"), hour (0-23). Nothing beyond these is real.
export const getSchedules = () => api.get("/api/analytics/schedules");
export const createSchedule = (floorIdx, { machine_id, scan_type, frequency, hour }) =>
  api.post(`/api/floors/${floorIdx}/schedules`, { machine_id, scan_type, frequency, hour });
export const deleteSchedule = (floorIdx, scheduleId) =>
  api.delete(`/api/floors/${floorIdx}/schedules/${scheduleId}`);
export const toggleSchedule = (floorIdx, scheduleId) =>
  api.patch(`/api/floors/${floorIdx}/schedules/${scheduleId}/toggle`);

// --- Presets (real routes: master_server.py's own /api/presets, backed by
// presets.json — not per-floor, so no floorIdx param here). Real allowed
// command_type set: scan, boost, clean, fix, rollback, exec. "exec" presets
// require both script + signature (signed offline via tools/sign_script.py). ---
export const getPresets = () => api.get("/api/presets");
export const createPreset = (body) => api.post("/api/presets", body);
export const updatePreset = (presetId, body) => api.put(`/api/presets/${presetId}`, body);
export const deletePreset = (presetId) => api.delete(`/api/presets/${presetId}`);
export const runPreset = (presetId, { floor_idx, machine_id, passphrase }) =>
  api.post(`/api/presets/${presetId}/run`, { floor_idx, machine_id, passphrase });

// --- Audit Logs (real routes: server/routes/audit.py's tamper-proof SHA256
// log system, aggregated via master_server.py's /api/analytics/audit/logs and
// proxied per-floor for verify/export). Real fields confirmed via a live
// response: id, machine_id, hostname, user_id, username, action, detail,
// status ("ok"/"warning"/"critical"), timestamp, hash (16-char preview),
// full_hash, floor_idx, floor_name. Nothing beyond these is real. ---
export const getAuditLogs = () => api.get("/api/analytics/audit/logs");
export const verifyAuditLog = (floorIdx, logId) =>
  api.get(`/api/floors/${floorIdx}/audit/logs/verify/${logId}`);
// Export is a real per-floor CSV download (StreamingResponse) — same-origin
// browser navigation carries the session cookie automatically, so this is a
// plain URL for an <a>/window.open, not an axios call.
export const auditLogExportUrl = (floorIdx) => `${window.location.origin}/api/floors/${floorIdx}/audit/logs/export`;

// --- Reports (real routes: server/routes/reports.py, aggregated via
// master_server.py's /api/analytics/reports). Real fields confirmed via a
// live response: id, machine_id, filename, size_kb, created_at, floor_idx,
// floor_name. Generation is real per-floor POST; download is a real
// FileResponse, so — same as audit export — a plain URL, not an axios call. ---
export const getReports = () => api.get("/api/analytics/reports");
export const generateMachineReport = (floorIdx, machineId) =>
  api.post(`/api/floors/${floorIdx}/reports/${machineId}`);
export const generateFleetReport = (floorIdx) =>
  api.post(`/api/floors/${floorIdx}/reports/fleet`, {});
export const generateAuditReport = (floorIdx, machineIds) =>
  api.post(`/api/floors/${floorIdx}/reports/audit`, machineIds && machineIds.length ? { machine_ids: machineIds } : {});
export const reportDownloadUrl = (floorIdx, reportId) => `${window.location.origin}/api/floors/${floorIdx}/reports/${reportId}/download`;
export const deleteReport = (floorIdx, reportId) =>
  api.delete(`/api/floors/${floorIdx}/reports/${reportId}`);

// --- Floors / machines (real route: master_server.py's /api/aggregate,
// backed by fetch_floor_summary which calls each floor's real /api/machines
// + /api/machines/pending). Real per-machine fields confirmed via a live
// response: id, hostname, ip, os_name, kernel, site_id, status, last_seen —
// nothing beyond these is real, so the UI only shows these. ---
export const getAggregate = () => api.get("/api/aggregate");
// Create a new floor (real route: master_server.py's POST /api/floors/admin/create).
// Real request fields: name, url, username, password — all required, all plain
// strings; password is stored encrypted-at-rest server-side (Fernet), never
// echoed back. Real response fields confirmed via source: ok, idx, name, url,
// baked_trust (always false immediately after creation), note (a real
// human-readable caveat string — display it verbatim, don't paraphrase it,
// since it explains the reassignment-trust gap precisely).
export const createFloor = ({ name, url, username, password }) =>
  api.post("/api/floors/admin/create", { name, url, username, password });
export const approveMachine = (floorIdx, machineId, targetFloorIdx) =>
  api.post(`/api/floors/${floorIdx}/machines/${machineId}/approve`, targetFloorIdx != null ? { target_floor_idx: Number(targetFloorIdx) } : {});
export const rejectMachine = (floorIdx, machineId) =>
  api.post(`/api/floors/${floorIdx}/machines/${machineId}/reject`);
// Real constraint (per the route's own docstring): the target machine must
// already be enrolled AND currently online — reassigning an offline machine
// is expected to fail server-side, not something this UI works around.
export const reassignMachine = (floorIdx, machineId, targetFloorIdx) =>
  api.post(`/api/floors/${floorIdx}/machines/${machineId}/reassign`, { target_floor_idx: Number(targetFloorIdx) });
// Fleet-wide command — real route dispatches to every ONLINE machine across
// all reachable floors when no explicit targets are given (server-side DB
// query per floor, never a per-machine HTTP fan-out from master).
export const dispatchFleetCommand = (type, params = {}) =>
  api.post(`/api/fleet/command`, { type, params });

// --- Whitelabel (real routes: server/routes/whitelabel.py. Master-
// authoritative by design — saving here pushes the SAME config to both
// floors via master_server.py's proxy, so branding never diverges between
// floors. Real WhiteLabelConfig fields: company_name, logo_text,
// logo_subtext, primary_color, accent_color, sidebar_bg, main_bg, card_bg,
// powered_by, support_email, support_url, dashboard_title, favicon_emoji. ---
export const getWhitelabel = () => api.get("/api/whitelabel");
export const updateWhitelabel = (body) => api.post("/api/whitelabel", body);
export const resetWhitelabel = () => api.post("/api/whitelabel/reset");

// --- Backup (real routes: server/routes/backup.py, aggregated via
// master_server.py's /api/analytics/backups + per-floor create/restore +
// a real /api/backup/all convenience action). Real fields confirmed via a
// live response: filename, path, size_kb, created, floor_idx, floor_name. ---
export const getBackups = () => api.get("/api/analytics/backups");
export const createBackup = (floorIdx) => api.post(`/api/floors/${floorIdx}/backup/create`);
export const restoreBackup = (floorIdx, filename) => api.post(`/api/floors/${floorIdx}/backup/restore/${filename}`);
export const backupAllFloors = () => api.post("/api/backup/all");

// --- Sites (real routes: server/routes/sites.py, aggregated via
// master_server.py's /api/sites + per-floor create/delete — a site always
// belongs to exactly one floor's DB, so create/delete are floor-scoped
// even though the list itself is merged). Real fields: id, name,
// machine_count, floor_idx, floor_name. ---
export const getSites = () => api.get("/api/sites");
export const createSite = (floorIdx, name) => api.post(`/api/floors/${floorIdx}/sites`, { name });
export const deleteSite = (floorIdx, siteId) => api.delete(`/api/floors/${floorIdx}/sites/${siteId}`);


// --- Notifications (real routes: server/settings/notifications endpoints,
// Master-authoritative — GET reads floors[0], POST pushes the same config to
// BOTH floors via master_server.py's proxy, same 207/results shape as
// Whitelabel. Real NotifyConfig fields: slack_webhook, teams_webhook,
// alert_email, smtp_host, smtp_port, smtp_user, smtp_pass (write-only — GET
// never returns it, only booleans smtp_configured/slack_configured/
// teams_configured). Test fires a real notification via
// /api/settings/notifications/test {type: "slack"|"teams"|"email"}. ---
export const getNotifications = () => api.get("/api/settings/notifications");
export const updateNotifications = (body) => api.post("/api/settings/notifications", body);
export const testNotification = (type) => api.post("/api/settings/notifications/test", { type });

export default api;
