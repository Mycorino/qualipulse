import client from "./client";

export interface PanelAttributeOption {
  value: string;
  label: string;
}

export interface PanelAttribute {
  id: string;
  category: string;
  type: "single" | "multi" | "bool" | "scale";
  is_sensitive: boolean;
  priority: number;
  label: string;
  options: PanelAttributeOption[];
}

export interface PanelCompleteness {
  answered_count: number;
  total_count: number;
  percent: number;
}

export type PanelAnswerValue = string | string[] | boolean;

export interface PanelMe {
  email: string;
  first_name: string | null;
  sensitive_consent: boolean;
  completeness: PanelCompleteness;
  answers: Record<string, PanelAnswerValue>;
  attributes: PanelAttribute[];
}

export async function getMyPanel(token: string, lang: string): Promise<PanelMe> {
  const { data } = await client.get<PanelMe>("/panel/me", { params: { token, lang } });
  return data;
}

export async function savePanelAnswers(
  token: string,
  answers: { attribute_id: string; value: PanelAnswerValue }[]
): Promise<{ saved: number; rejected: string[]; completeness: PanelCompleteness }> {
  const { data } = await client.post("/panel/answers", { token, answers });
  return data;
}

export async function grantSensitiveConsent(
  token: string,
  lang: string
): Promise<{ sensitive_consent: boolean; attributes: PanelAttribute[] }> {
  const { data } = await client.post("/panel/sensitive-consent", { token }, { params: { lang } });
  return data;
}

export async function requestPanelAccess(email: string, lang?: string): Promise<void> {
  await client.post("/panel/request-access", { email, lang });
}

export async function joinPanel(params: {
  email: string;
  first_name?: string;
  lang?: string;
  consent: boolean;
}): Promise<void> {
  await client.post("/panel/join", params);
}

export async function confirmPanelJoin(token: string): Promise<{ token: string }> {
  const { data } = await client.post<{ token: string }>("/panel/join/confirm", { token });
  return data;
}
