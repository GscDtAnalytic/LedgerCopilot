/**
 * Client-side auth utilities — JWT storage + user info (Phase 4).
 * Token is stored in localStorage; parsed without signature verification
 * (the backend verifies on every authenticated request).
 */

const TOKEN_KEY = "lc_token";

export interface AuthUser {
  user_id: string;
  email: string;
  role: "analyst" | "approver" | "admin";
  org_id: string;
}

function parseJwtPayload(token: string): AuthUser | null {
  try {
    const [, payloadB64] = token.split(".");
    const json = atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/"));
    const data = JSON.parse(json) as Record<string, string>;
    return {
      user_id: data["sub"],
      email: data["email"],
      role: data["role"] as AuthUser["role"],
      org_id: data["org_id"],
    };
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  // Also mirror into a cookie so Server Components (which cannot read localStorage)
  // can forward the JWT to the API. max-age matches the backend JWT TTL (8h).
  if (typeof document !== "undefined") {
    document.cookie = `${TOKEN_KEY}=${token}; path=/; samesite=lax; max-age=28800`;
  }
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  if (typeof document !== "undefined") {
    document.cookie = `${TOKEN_KEY}=; path=/; max-age=0`;
  }
}

export function getCurrentUser(): AuthUser | null {
  const token = getToken();
  if (!token) return null;
  return parseJwtPayload(token);
}

export const ROLE_LABELS: Record<string, string> = {
  analyst: "Analyst",
  approver: "Approver",
  admin: "Admin",
};
