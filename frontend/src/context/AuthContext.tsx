"use client";

import {
  createContext,
  ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";

import {
  apiFetch,
  login as apiLogin,
  logout as apiLogout,
  restoreSession,
} from "@/lib/api";


type User = {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
};


type AuthContextType = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};


const AuthContext = createContext<AuthContextType | undefined>(
  undefined,
);


export function AuthProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadCurrentUser() {
    const response = await apiFetch("/auth/me");

    if (!response.ok) {
      setUser(null);
      return;
    }

    const data: User = await response.json();
    setUser(data);
  }


  useEffect(() => {
    async function initializeAuth() {
      try {
        const restored = await restoreSession();
        if (restored) await loadCurrentUser();
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    }

    initializeAuth();
  }, []);


  async function login(
    email: string,
    password: string,
  ) {
    await apiLogin({
      email,
      password,
    });

    await loadCurrentUser();
  }


  async function logout() {
    await apiLogout();
    setUser(null);
  }


  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}


export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error(
      "useAuth must be used inside AuthProvider",
    );
  }

  return context;
}