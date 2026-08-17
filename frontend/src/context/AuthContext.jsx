import { createContext, useContext, useEffect, useState, useCallback } from "react";
import client from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [roleLabel, setRoleLabel] = useState("");
  const [hasClockInOut, setHasClockInOut] = useState(true);
  const [loading, setLoading] = useState(true);

  const hydrate = useCallback(async () => {
    const token = localStorage.getItem("hrms_token");
    if (!token) {
      setLoading(false);
      return;
    }
    try {
      const { data } = await client.get("/auth/me");
      setUser(data.user);
      setRoleLabel(data.role_label);
      setHasClockInOut(data.has_clock_in_out);
    } catch (e) {
      localStorage.removeItem("hrms_token");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const login = async (email, password) => {
    const { data } = await client.post("/auth/login", { email, password });
    localStorage.setItem("hrms_token", data.access_token);
    setUser(data.user);
    setRoleLabel(data.role_label);
    setHasClockInOut(data.has_clock_in_out);
    return data;
  };

  const logout = () => {
    localStorage.removeItem("hrms_token");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, roleLabel, hasClockInOut, loading, login, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
