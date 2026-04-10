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
  website_url: string | null;
  business_summary: string | null;
  research_experience: string | null;
  primary_region: string | null;
  goals_freeform: string | null;
  preferred_language: string;
  slack_webhook_url: string | null;
}

export interface OnboardingProfile {
  name?: string;
  company_size?: string;
  role?: string;
  industry?: string;
  use_case?: string;
  website_url?: string;
  business_summary?: string;
  research_experience?: string;
  primary_region?: string;
  goals_freeform?: string;
  preferred_language?: string;
}

export async function signup(
  name: string,
  email: string,
  password: string,
  opts?: { plan?: string; refCode?: string; preferredLanguage?: string }
): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>("/auth/signup", {
    name,
    email,
    password,
    plan: opts?.plan,
    ref_code: opts?.refCode,
    preferred_language: opts?.preferredLanguage,
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

export interface AnalyseWebsiteResponse {
  business_summary: string;
  industry?: string | null;
}

export async function analyseWebsite(websiteUrl: string): Promise<AnalyseWebsiteResponse> {
  const { data } = await client.post<AnalyseWebsiteResponse>("/auth/website-intel", {
    website_url: websiteUrl,
  });
  return data;
}

export async function updateSlackWebhook(url: string | null): Promise<{ slack_webhook_url: string | null }> {
  const { data } = await client.put<{ slack_webhook_url: string | null }>("/auth/me/slack", {
    slack_webhook_url: url,
  });
  return data;
}

export async function testSlackWebhook(url?: string | null): Promise<{ message: string }> {
  const { data } = await client.post<{ message: string }>("/auth/me/slack/test", {
    slack_webhook_url: url ?? null,
  });
  return data;
}
