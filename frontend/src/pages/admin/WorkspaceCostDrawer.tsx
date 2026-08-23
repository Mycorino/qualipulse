import { useEffect, useState } from "react";
import type { AxiosInstance } from "axios";
import { useTranslation } from "react-i18next";
import { Card, DataTable, Drawer, Kpi, Skeleton, StackBar, WindowPicker, fmtDate, fmtInt, fmtUsd } from "./ui";
import type { InterviewEconomics } from "./economics";
import { BUCKET_LABELS } from "./economics";

interface ProjectRow {
  project_id: string;
  name: string;
  is_demo: boolean;
  created_at: string | null;
  archived: boolean;
  cost_usd: number;
  completed_interviews: number;
  cost_per_interview_usd: number | null;
}

interface InterviewRow {
  participant_id: string;
  display_name: string | null;
  project_name: string;
  status: string;
  quality_label: string | null;
  started_at: string | null;
  duration_minutes: number | null;
  turns: number;
  audio_minutes: number;
  cost_usd: number;
  stt_usd: number;
  tts_usd: number;
  llm_usd: number;
  other_usd: number;
}

interface CompanyReport {
  company_id: string;
  name: string;
  email: string;
  days: number | null;
  window_cost_usd: number;
  total_cost_usd: number;
  by_operation: { operation: string; area: string; calls: number; cost_usd: number }[];
  by_project: ProjectRow[];
  interview_economics: InterviewEconomics;
  interviews: InterviewRow[];
}

const QUALITY_TONE: Record<string, string> = { strong: "adm-pill--good", good: "adm-pill--good", low: "adm-pill--bad", poor: "adm-pill--bad" };

export default function WorkspaceCostDrawer({
  client,
  companyId,
  days: initialDays,
  onClose,
}: {
  client: () => AxiosInstance;
  companyId: string;
  days: number;
  onClose: () => void;
}) {
  const { t } = useTranslation("admin");
  const [days, setDays] = useState(initialDays);
  const [data, setData] = useState<CompanyReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    client()
      .get<CompanyReport>(`/admin/costs/company/${companyId}`, { params: { days } })
      .then((r) => { if (!cancelled) setData(r.data); })
      .catch(() => { if (!cancelled) setError(t("costs.loadFailed", "Could not load costs.")); });
    return () => { cancelled = true; };
  }, [client, companyId, days, t]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const windowLabel = (d: number) => (d === 0 ? t("costs.allTime", "All time") : t("overview.windowDays", "{{n}}d", { n: d }));

  return (
    <Drawer title={data?.name ?? "…"} sub={data?.email} onClose={onClose}>
      <div className="adm-toolbar">
        <span className="adm-toolbar__hint">{t("costs.drawerHint", "AI spend for this workspace. Interview rows always show the interview's full cost, whatever the window.")}</span>
        <WindowPicker value={days} onChange={setDays} options={[7, 30, 90, 0]} labels={windowLabel} />
      </div>
      {error && <div className="adm-error">{error}</div>}
      {!data ? (
        <Skeleton h={300} />
      ) : (
        <>
          <div className="adm-grid adm-grid--kpi">
            <Kpi label={days ? t("costs.windowSpend", "Spend in window") : t("costs.allTime", "All time")} value={fmtUsd(data.window_cost_usd)} accent foot={days ? t("costs.allTimeFoot", "{{v}} all time", { v: fmtUsd(data.total_cost_usd) }) : undefined} />
            <Kpi label={t("costs.perCompleted", "Per completed interview")} value={fmtUsd(data.interview_economics.cost_per_completed_usd, 3)} foot={t("costs.nCompleted", "{{n}} completed", { n: fmtInt(data.interview_economics.completed_interviews) })} />
            <Kpi label={t("costs.overhead", "Study overhead")} value={fmtUsd(Math.max(0, data.window_cost_usd - data.interview_economics.total_cost_usd))} foot={t("costs.overheadFoot", "analysis, copilot, translation")} />
          </div>

          <div className="adm-grid adm-grid--2">
            <Card title={t("costs.byOperation", "By operation")}>
              <StackBar parts={data.by_operation.map((o) => ({ label: o.operation, value: o.cost_usd }))} />
            </Card>
            <Card title={t("costs.breakdownTitle", "Inside an interview")}>
              <StackBar parts={Object.entries(data.interview_economics.breakdown).map(([k, v]) => ({ label: BUCKET_LABELS[k] ?? k, value: v }))} />
            </Card>
          </div>

          <Card title={t("costs.byStudy", "By study")} className="adm-grid">
            <DataTable
              rows={data.by_project}
              rowKey={(r) => r.project_id}
              defaultSort={{ key: "cost_usd", dir: "desc" }}
              columns={[
                { key: "name", label: t("costs.colStudy", "Study"), sortable: true, render: (r) => <><span className="primary">{r.name}</span>{r.is_demo && <span className="adm-pill adm-pill--demo" style={{ marginLeft: 6 }}>demo</span>}{r.archived && <span className="adm-pill" style={{ marginLeft: 6 }}>{t("costs.archived", "archived")}</span>}</> },
                { key: "created_at", label: t("costs.colCreated", "Created"), sortable: true, render: (r) => <span className="dim">{fmtDate(r.created_at)}</span> },
                { key: "completed_interviews", label: t("costs.colInterviewsAll", "Interviews"), num: true, sortable: true, render: (r) => fmtInt(r.completed_interviews) },
                { key: "cost_per_interview_usd", label: t("costs.colPerInterview", "/ interview"), num: true, sortable: true, render: (r) => fmtUsd(r.cost_per_interview_usd, 3) },
                { key: "cost_usd", label: t("costs.colCost", "Cost"), num: true, sortable: true, bar: true, render: (r) => fmtUsd(r.cost_usd) },
              ]}
            />
          </Card>

          <Card title={t("costs.interviews", "Interviews")} sub={t("costs.interviewsSub", "Most recent first, up to 50. Split: Claude turns + warmup, speech-to-text, text-to-speech, and the rest (cleanup, quality).")}>
            <DataTable
              rows={data.interviews}
              rowKey={(r) => r.participant_id}
              defaultSort={{ key: "started_at", dir: "desc" }}
              empty={t("costs.noInterviews", "No interviews in this window.")}
              columns={[
                { key: "display_name", label: t("costs.colParticipant", "Participant"), sortable: true, render: (r) => <><div className="primary">{r.display_name || t("costs.anonymous", "Anonymous")}</div><div className="muted">{r.project_name}</div></> },
                { key: "started_at", label: t("costs.colStarted", "Started"), sortable: true, render: (r) => <span className="dim">{fmtDate(r.started_at)}</span> },
                { key: "status", label: t("costs.colStatus", "Status"), render: (r) => <><span className={`adm-pill${r.status === "completed" ? " adm-pill--good" : ""}`}>{r.status}</span>{r.quality_label && <span className={`adm-pill ${QUALITY_TONE[r.quality_label] ?? ""}`} style={{ marginLeft: 4 }}>{r.quality_label}</span>}</> },
                { key: "turns", label: t("costs.colTurns", "Turns"), num: true, sortable: true, render: (r) => fmtInt(r.turns) },
                { key: "duration_minutes", label: t("costs.colMinutes", "Min"), num: true, sortable: true, render: (r) => r.duration_minutes ?? "-" },
                { key: "llm_usd", label: "Claude", num: true, sortable: true, render: (r) => fmtUsd(r.llm_usd, 3) },
                { key: "stt_usd", label: "STT", num: true, sortable: true, render: (r) => fmtUsd(r.stt_usd, 3) },
                { key: "tts_usd", label: "TTS", num: true, sortable: true, render: (r) => fmtUsd(r.tts_usd, 3) },
                { key: "cost_usd", label: t("costs.colTotal", "Total"), num: true, sortable: true, bar: true, render: (r) => <strong>{fmtUsd(r.cost_usd, 3)}</strong> },
              ]}
            />
          </Card>
        </>
      )}
    </Drawer>
  );
}
