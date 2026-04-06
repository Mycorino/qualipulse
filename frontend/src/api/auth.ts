import client from "./client";

export interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
}

export interface CompanyResponse {
  id: string;
  name: string;
  email: string;
  email_verified: boolean;
  company_size: string | null;
  role: string | null;
  industry: string | null;
  use_case: string | null;
  onboarding_completed: boolean;
  subscription_tier: string;
  trial_ends_at: string | null;
  created_at: string;
}

export interface OnboardingProfile {
  name?: string;
  company_size?: string;
  role?: string;
  industry?: string;
  use_case?: string;
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

export async function verifyEmail(token: string): Promise<void> {
  await client.post(`/auth/verify-email?token=${encodeURIComponent(token)}`);
}

export async function resendVerification(): Promise<void> {
  await client.post("/auth/resend-verification");
}

export async function saveOnboardingProfile(profile: OnboardingProfile): Promise<CompanyResponse> {
  const { data } = await client.patch<CompanyResponse>("/auth/onboarding", profile);
  return data;
}

export async function completeOnboarding(profile: OnboardingProfile): Promise<CompanyResponse> {
  const { data } = await client.post<CompanyResponse>("/auth/onboarding", profile);
  return data;
}
