import client from "./client";

// ── Cross-study synthesis (decision memos) ──────────────────────────────────

export interface SynthesisSummary {
  id: string;
  name: string;
  status: "generating" | "ready" | "failed";
  study_count: number;
  study_names: string[];
  decision_question: string | null;
  generated_at: string | null;
  created_at: string | null;
  error: string | null;
}

export interface SynthesisDetail {
  id: string;
  name: string;
  status: "generating" | "ready" | "failed";
  decision_question: string | null;
  study_ids: string[];
  report: Record<string, unknown> | null;
  error: string | null;
  generated_at: string | null;
}

export async function listSyntheses(): Promise<SynthesisSummary[]> {
  const { data } = await client.get<SynthesisSummary[]>("/synthesis/");
  return data;
}

export async function createSynthesis(input: {
  study_ids: string[];
  name?: string;
  decision_question?: string;
}): Promise<{ id: string; status: string }> {
  const { data } = await client.post("/synthesis/", input);
  return data;
}

export async function getSynthesis(id: string): Promise<SynthesisDetail> {
  const { data } = await client.get<SynthesisDetail>(`/synthesis/${id}`);
  return data;
}

export async function deleteSynthesis(id: string): Promise<void> {
  await client.delete(`/synthesis/${id}`);
}

export async function fetchSynthesisMemoHtml(id: string): Promise<Blob> {
  const { data } = await client.get(`/synthesis/${id}/report.html`, {
    responseType: "blob",
  });
  return data;
}
