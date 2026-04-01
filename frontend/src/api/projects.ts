import client from "./client";

export interface QuestionCreate {
  section_index: number;
  section_title: string;
  question_index: number;
  main_question: string;
  interview_notes?: string;
  desired_learning?: string;
}

export interface ProjectCreate {
  name: string;
  language: string;
  interview_duration_minutes?: number;
  system_prompt?: string;
  research_objective?: string;
  questions: QuestionCreate[];
}

export interface QuestionResponse {
  id: string;
  section_index: number;
  section_title: string;
  question_index: number;
  main_question: string;
  interview_notes?: string;
  desired_learning?: string;
}

export interface ProjectResponse {
  id: string;
  company_id: string;
  name: string;
  language: string;
  interview_duration_minutes: number;
  system_prompt?: string;
  research_objective?: string;
  created_at: string;
  questions: QuestionResponse[];
}

export interface ProjectListItem {
  id: string;
  name: string;
  language: string;
  created_at: string;
  question_count: number;
}

export interface InterviewLink {
  id: string;
  project_id: string;
  token: string;
  is_active: boolean;
  created_at: string;
}

export interface ParticipantResponse {
  id: string;
  display_name: string | null;
  status: string;
  started_at: string;
  completed_at: string | null;
}

export interface TranscriptTurn {
  turn_index: number;
  question_text: string;
  response_transcript: string | null;
  is_follow_up: boolean;
  created_at: string;
}

export async function listProjects(): Promise<ProjectListItem[]> {
  const { data } = await client.get<ProjectListItem[]>("/projects/");
  return data;
}

export async function getProject(id: string): Promise<ProjectResponse> {
  const { data } = await client.get<ProjectResponse>(`/projects/${id}`);
  return data;
}

export async function createProject(
  body: ProjectCreate
): Promise<ProjectResponse> {
  const { data } = await client.post<ProjectResponse>("/projects/", body);
  return data;
}

export async function updateProject(
  id: string,
  body: ProjectCreate
): Promise<ProjectResponse> {
  const { data } = await client.put<ProjectResponse>(`/projects/${id}`, body);
  return data;
}

export async function importProjectCSV(
  name: string,
  language: string,
  csvFile: File
): Promise<ProjectResponse> {
  const form = new FormData();
  form.append("name", name);
  form.append("language", language);
  form.append("csv_file", csvFile);
  const { data } = await client.post<ProjectResponse>(
    "/projects/import",
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data;
}

export async function deleteProject(id: string): Promise<void> {
  await client.delete(`/projects/${id}`);
}

export async function createLink(
  projectId: string
): Promise<InterviewLink> {
  const { data } = await client.post<InterviewLink>(
    `/projects/${projectId}/links`
  );
  return data;
}

export async function getLinks(
  projectId: string
): Promise<InterviewLink[]> {
  const { data } = await client.get<InterviewLink[]>(
    `/projects/${projectId}/links`
  );
  return data;
}

export async function getParticipants(
  projectId: string
): Promise<ParticipantResponse[]> {
  const { data } = await client.get<ParticipantResponse[]>(
    `/projects/${projectId}/participants`
  );
  return data;
}

export async function getTranscript(
  projectId: string,
  participantId: string
): Promise<TranscriptTurn[]> {
  const { data } = await client.get<{ participant: ParticipantResponse; turns: TranscriptTurn[] }>(
    `/projects/${projectId}/participants/${participantId}/transcript`
  );
  return data.turns;
}

export interface AnalysisTheme {
  title: string;
  summary: string;
  quotes: string[];
  frequency: string;
}
export interface AnalysisJTBD {
  job: string;
  insight: string;
  frequency: string;
}
export interface AnalysisTension {
  tension: string;
  detail: string;
}
export interface AnalysisReport {
  summary: string;
  themes: AnalysisTheme[];
  jobs_to_be_done: AnalysisJTBD[];
  tensions: AnalysisTension[];
  recommendations: string[];
  confidence: string;
  participant_count: number;
}
export interface AnalysisResponse {
  status: "none" | "generating" | "ready" | "failed";
  completed_count: number;
  participant_count: number;
  generated_at: string | null;
  report: AnalysisReport | null;
  error: string | null;
}

export async function getAnalysis(projectId: string): Promise<AnalysisResponse> {
  const { data } = await client.get<AnalysisResponse>(`/projects/${projectId}/analysis`);
  return data;
}

export async function triggerAnalysis(projectId: string): Promise<void> {
  await client.post(`/projects/${projectId}/analysis`);
}

export async function exportCSV(projectId: string): Promise<Blob> {
  const { data } = await client.get(`/projects/${projectId}/export`, {
    responseType: "blob",
  });
  return data;
}
