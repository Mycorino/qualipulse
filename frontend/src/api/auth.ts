import client from "./client";

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface CompanyResponse {
  id: string;
  name: string;
  email: string;
  created_at: string;
}

export async function signup(
  name: string,
  email: string,
  password: string
): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>("/auth/signup", {
    name,
    email,
    password,
  });
  return data;
}

export async function login(
  email: string,
  password: string
): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>("/auth/login", {
    email,
    password,
  });
  return data;
}

export async function getMe(): Promise<CompanyResponse> {
  const { data } = await client.get<CompanyResponse>("/auth/me");
  return data;
}

export async function refreshToken(refreshToken: string): Promise<{ access_token: string; refresh_token: string }> {
  const { data } = await client.post("/auth/refresh", { refresh_token: refreshToken });
  return data;
}

export async function requestPasswordReset(email: string): Promise<void> {
  await client.post("/auth/password-reset/request", { email });
}

export async function confirmPasswordReset(token: string, newPassword: string): Promise<void> {
  await client.post("/auth/password-reset/confirm", { token, new_password: newPassword });
}
