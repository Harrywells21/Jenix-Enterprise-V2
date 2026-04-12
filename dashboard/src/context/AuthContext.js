import { createContext, useContext, useState } from "react";
import { setToken } from "../api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user,  setUser] = useState(null);
  const [token, setTok]  = useState(null);

  const loginSuccess = (tokenStr, userData) => {
    setTok(tokenStr);
    setToken(tokenStr);
    setUser(userData);
  };

  const logout = () => {
    setTok(null);
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, loginSuccess, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
