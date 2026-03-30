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
