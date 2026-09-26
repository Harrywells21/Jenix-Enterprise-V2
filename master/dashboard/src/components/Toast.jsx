import { createContext, useCallback, useContext, useState } from "react";

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((message, type = "success") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500);
  }, []);

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      <div style={{
        position: "fixed", top: 20, right: 20, zIndex: 9999,
        display: "flex", flexDirection: "column", gap: 8,
      }}>
        {toasts.map((t) => (
          <div key={t.id} style={{
            padding: "11px 16px",
            minWidth: 220,
            background: t.type === "error" ? "var(--rose-dim)" : t.type === "info" ? "var(--cyan-dim)" : "var(--emerald-dim)",
            border: `1px solid ${t.type === "error" ? "var(--rose)" : t.type === "info" ? "var(--cyan)" : "var(--emerald)"}44`,
            borderRadius: "var(--radius-md)",
            color: t.type === "error" ? "var(--rose)" : t.type === "info" ? "var(--cyan)" : "var(--emerald)",
            fontSize: 13, fontFamily: "var(--font-body)",
            boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
            animation: "slideIn 0.25s var(--ease-out) both",
            display: "flex", alignItems: "center", gap: 8,
          }}>
            <span style={{ fontFamily: "var(--font-mono)" }}>
              {t.type === "error" ? "✗" : t.type === "info" ? "ℹ" : "✓"}
            </span>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
