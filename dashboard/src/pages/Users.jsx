import { useState, useEffect } from "react";
import { getUsers, createUser, deactivateUser } from "../api";
import { useAuth } from "../context/AuthContext";

export default function Users() {
  const { user }  = useAuth();
  const [users,   setUsers] = useState([]);
  const [form,    setForm]  = useState({ name:"", email:"", password:"", role:"viewer" });
  const [toast,   setToast] = useState("");

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(""), 3000); };

  useEffect(() => {
    getUsers().then(r => setUsers(r.data)).catch(() => {});
  }, []);

  const handleCreate = async () => {
    if (!form.name || !form.email || !form.password)
      return showToast("All fields required");
    try {
      await createUser(form);
      const r = await getUsers();
      setUsers(r.data);
      setForm({ name:"", email:"", password:"", role:"viewer" });
      showToast("✅ User created");
    } catch (e) {
      showToast(`❌ ${e.response?.data?.detail || e.message}`);
    }
  };

  const handleDeactivate = async (id) => {
    await deactivateUser(id);
    setUsers(prev => prev.map(u =>
      u.id === id ? { ...u, is_active:false } : u));
    showToast("User deactivated");
  };

  if (user?.role !== "admin") return (
    <div style={{ color:"#f44336", marginTop:"80px", textAlign:"center" }}>
      Admin access required.
    </div>
  );

  return (
    <div>
      {toast && (
        <div style={{
          position:"fixed", top:"20px", right:"20px",
          background:"#1a1a2e", border:"1px solid #2a2a3e",
          borderRadius:"8px", padding:"12px 20px",
          color:"#e0e0e0", fontSize:"13px", zIndex:1000
        }}>{toast}</div>
      )}

      <h1 style={{ color:"#e0e0e0", fontSize:"22px",
                   fontWeight:700, marginBottom:"24px" }}>
        User Management
      </h1>

      <div style={{
        background:"#13131f", border:"1px solid #2a2a3e",
        borderRadius:"10px", padding:"20px", marginBottom:"24px"
      }}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"12px" }}>
          CREATE USER
        </div>
        <div style={{ display:"flex", gap:"10px", flexWrap:"wrap" }}>
          {[
            { key:"name",     placeholder:"Full name", type:"text"     },
            { key:"email",    placeholder:"Email",     type:"email"    },
            { key:"password", placeholder:"Password",  type:"password" },
          ].map(({ key, placeholder, type }) => (
            <input key={key} type={type} placeholder={placeholder}
              value={form[key]}
              onChange={e => setForm(p => ({ ...p, [key]:e.target.value }))}
              style={{
                padding:"8px 12px", background:"#1a1a2e",
                border:"1px solid #2a2a3e", borderRadius:"8px",
                color:"#e0e0e0", fontSize:"13px", outline:"none"
              }}
            />
          ))}
          <select value={form.role}
            onChange={e => setForm(p => ({ ...p, role:e.target.value }))}
            style={{
              padding:"8px 12px", background:"#1a1a2e",
              border:"1px solid #2a2a3e", borderRadius:"8px",
              color:"#e0e0e0", fontSize:"13px", outline:"none"
            }}>
            <option value="viewer">Viewer</option>
            <option value="operator">Operator</option>
            <option value="admin">Admin</option>
          </select>
          <button onClick={handleCreate} style={{
            padding:"8px 20px", background:"#00bcd4",
            color:"#000", border:"none", borderRadius:"8px",
            fontWeight:700, fontSize:"13px", cursor:"pointer"
          }}>Create</button>
        </div>
      </div>

      <div style={{
        background:"#13131f", border:"1px solid #2a2a3e",
        borderRadius:"10px", padding:"20px"
      }}>
        <div style={{ color:"#aaa", fontSize:"12px",
                      fontWeight:600, marginBottom:"12px" }}>
          ALL USERS ({users.length})
        </div>
        <table style={{ width:"100%", borderCollapse:"collapse", fontSize:"13px" }}>
          <thead>
            <tr style={{ color:"#666" }}>
              {["Name","Email","Role","Status","Action"].map(h => (
                <th key={h} style={{ textAlign:"left", padding:"8px",
                                     borderBottom:"1px solid #2a2a3e" }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} style={{ borderBottom:"1px solid #1a1a2e" }}>
                <td style={{ padding:"8px", color:"#e0e0e0" }}>{u.name}</td>
                <td style={{ padding:"8px", color:"#aaa"   }}>{u.email}</td>
                <td style={{ padding:"8px", color:"#00bcd4",
                             textTransform:"capitalize" }}>{u.role}</td>
                <td style={{ padding:"8px",
                  color: u.is_active ? "#4caf50" : "#f44336" }}>
                  {u.is_active ? "Active" : "Inactive"}
                </td>
                <td style={{ padding:"8px" }}>
                  {u.is_active && u.id !== 1 && (
                    <button onClick={() => handleDeactivate(u.id)} style={{
                      padding:"4px 10px", background:"#1a1a2e",
                      color:"#f44336", border:"1px solid #f44336",
                      borderRadius:"6px", fontSize:"12px", cursor:"pointer"
                    }}>Deactivate</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
