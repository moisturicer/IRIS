/** Claims embedded in IRIS access tokens (SRS / SDD Module 6). */
export interface JwtPayload {
  user_id?:    number;
  role_id?:    number;
  department?: string | null;
  exp?:        number;
}

export function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;

    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
    const json   = atob(padded);
    return JSON.parse(json) as JwtPayload;
  } catch {
    return null;
  }
}

export function isJwtExpired(payload: JwtPayload): boolean {
  if (payload.exp == null) return true;
  return payload.exp * 1000 <= Date.now();
}
