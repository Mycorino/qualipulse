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
  first_name: string | null;
  last_name: string | null;
  company_size: string | null;
  role: string | null;
  industry: string | null;
  use_case: string | null;
  occupation_description: string | null;
  selected_use_cases: string[] | null;
  onboarding_completed: boolean;
  onboarding_recap: string | null;
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
  // Business context
  value_proposition?: string | null;
  primary_competitors?: string | null;
  product_stage?: string | null;
  customer_type?: string | null;
  // Qualification signals
  interviews_per_month_target?: string | null;
  current_tool?: string | null;
  decision_role?: string | null;
  goals_classification?: string | null;
  // Monthly "what are you focused on right now?" prompt shown on the
  // Dashboard. Null when never set; ``current_priority_updated_at`` drives
  // the 30-day re-prompt cadence.
  current_priority?: string | null;
  current_priority_updated_at?: string | null;
}

export interface OnboardingProfile {
  name?: string;
  first_name?: string;
  last_name?: string;
  company_size?: string;
  role?: string;
  industry?: string;
  use_case?: string;
  occupation_description?: string;
  selected_use_cases?: string;  // comma-separated (backend stores as string)
  onboarding_recap?: string;
  website_url?: string;
  business_summary?: string;
  research_experience?: string;
  primary_region?: string;
  goals_freeform?: string;
  preferred_language?: string;
  // Business context
  value_proposition?: string;
  primary_competitors?: string;
  product_stage?: string;
  customer_type?: string;
  // Qualification signals
  interviews_per_month_target?: string;
  current_tool?: string;
  decision_role?: string;
}

export async function signup(
  name: string,
  email: string,
  password: string,
  opts?: { plan?: string; refCode?: string; preferredLanguage?: string; firstName?: string; lastName?: string }
): Promise<TokenResponse> {
  const { data } = await client.post<TokenResponse>("/auth/signup", {
    name,
    email,
    password,
    plan: opts?.plan,
    ref_code: opts?.refCode,
    preferred_language: opts?.preferredLanguage,
    first_name: opts?.firstName,
    last_name: opts?.lastName,
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
  // ISO-like code for the detected primary market (fr/be/ch/de/uk/es/it/
  // nl/pt/europe/us/ca/global/other). Frontend preselects the matching
  // chip in the onboarding flow.
  primary_country?: string | null;
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

export async function updateCurrentPriority(
  currentPriority: string | null
): Promise<CompanyResponse> {
  const { data } = await client.patch<CompanyResponse>("/auth/me/priority", {
    current_priority: currentPriority,
  });
  return data;
}

// ── Role classification (onboarding step 3) ──

export interface RoleClassificationResponse {
  canonical_tag: string;
  orientation: string;
  suggested_use_cases: string[];
  research_angle: string;
}

export async function classifyRole(payload: {
  role_title?: string;
  occupation_description?: string;
  industry?: string;
  business_summary?: string;
  language?: string;
}): Promise<RoleClassificationResponse> {
  const { data } = await client.post<RoleClassificationResponse>(
    "/auth/onboarding/classify-role",
    payload,
  );
  return data;
}

// ── Personalized recap (onboarding step 4) ──

export interface RecapResponse {
  recap: string;
}

export async function generateRecap(payload: {
  first_name?: string;
  last_name?: string;
  company_name?: string;
  role_title?: string;
  occupation_description?: string;
  research_experience?: string;
  industry?: string;
  business_summary?: string;
  selected_use_cases?: string[];
  goals_freeform?: string;
  language?: string;
}): Promise<RecapResponse> {
  const { data } = await client.post<RecapResponse>(
    "/auth/onboarding/generate-recap",
    payload,
  );
  return data;
}
