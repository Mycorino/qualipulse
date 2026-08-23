import { useEffect, useState } from "react";
import type { AxiosInstance } from "axios";
import { useTranslation } from "react-i18next";
import { BarChart, Card, DataTable, Delta, Kpi, Skeleton, StackBar, WindowPicker, fmtInt, fmtRelative, fmtUsd, pct } from "./ui";
import WorkspaceCostDrawer from "./WorkspaceCostDrawer";
import { EconomicsBlock } from "./economics";
import type { InterviewEconomics } from "./economics";

interface OperationRow {
  operation: string;
  area: string;
  calls: number;
  cost_usd: number;
  avg_cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  audio_seconds: number;
  characters: number;
}

export interface CompanyCostRow {
  company_id: string;
  name: string;
  email: string;
  has_ever_paid: boolean;
  plan_name: string | null;
  plan_is_legacy: boolean | null;
  created_at: string | null;
  last_interview_at: string | null;
  window_cost_usd: number;
  total_cost_usd: number;
  window_interviews: number;
  total_interviews: number;
  window_cost_per_interview_usd: number | null;
}

interface CostsReport {
  days: number | null;
  window_cost_usd: number;
  previous_window_cost_usd: number;
  change_pct: number | null;
  all_time_cost_usd: number;
  this_month_usd: number;
  by_operation: OperationRow[];
  by_area: { area: string; cost_usd: number }[];
  by_model: { model: string; calls: number; cost_usd: number }[];
  daily: { date: string; cost_usd: number; interview_cost_usd: number }[];
  interview_economics: InterviewEconomics;
  by_company: CompanyCostRow[];
}

const AREA_LABELS: Record<string, string> = {
  interviews: "Interviews",
  analysis: "Analysis",
  copilot: "Copilot",
  translation: "Translation",
  onboarding: "Onboarding",
  other: "Other",
};

export default function AdminCosts({
  client,
  openWorkspaceId,
  onOpenWorkspace,
  onCloseWorkspace,
}: {
  client: () => AxiosInstance;
  openWorkspaceId: string | null;
  onOpenWorkspace: (companyId: string) => void;
  onCloseWorkspace: () => void;
}) {
  const { t } = useTranslation("admin");
  const [days, setDays] = useState(30);
  const [data, setData] = useState<CostsReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    let cancelled = false;
    setError(null);
    client()
      .get<CostsReport>("/admin/costs", { params: { days } })
      .then((r) => { if (!cancelled) setData(r.data); })
      .catch(() => { if (!cancelled) setError(t("costs.loadFailed", "Could not load costs.")); });
    return () => { cancelled = true; };
  }, [client, days, t]);

  const windowLabel = (d: number) => (d === 0 ? t("costs.allTime", "All time") : t("overview.windowDays", "{{n}}d", { n: d }));
  const q = filter.trim().toLowerCase();
  const companies = data ? data.by_company.filter((c) => !q || c.name.toLowerCase().includes(q) || c.email.toLowerCase().includes(q) || (c.plan_name ?? "").toLowerCase().includes(q)) : [];
  const overhead = data ? data.window_cost_usd - data.interview_economics.total_cost_usd : 0;

  return (
    <div>
      <div className="adm-toolbar">
        <div>
          <h2>{t("costs.title", "AI spend")}</h2>
          <div className="adm-toolbar__hint">{t("costs.hint", "Every Claude, Whisper and TTS call, priced at list rates including prompt-cache discounts.")}</div>
        </div>
        <WindowPicker value={days} onChange={setDays} options={[7, 30, 90, 0]} labels={windowLabel} />
      </div>

      {error && <div className="adm-error">{error}</div>}

      {!data ? (
        <div className="adm-grid adm-grid--kpi">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} h={92} />)}</div>
      ) : (
        <>
          <div className="adm-grid adm-grid--kpi">
            <Kpi
              label={days ? t("costs.windowSpend", "Spend in window") : t("costs.allTime", "All time")}
              value={fmtUsd(data.window_cost_usd)}
              changePct={days ? data.change_pct : undefined}
              previous={days ? fmtUsd(data.previous_window_cost_usd) : undefined}
              invert
              accent
            />
            <Kpi label={t("costs.thisMonth", "This month")} value={fmtUsd(data.this_month_usd)} foot={t("costs.allTimeFoot", "{{v}} all time", { v: fmtUsd(data.all_time_cost_usd) })} />
            <Kpi label={t("costs.interviewSpend", "Interview spend")} value={fmtUsd(data.interview_economics.total_cost_usd)} foot={pct(data.interview_economics.total_cost_usd, data.window_cost_usd) + " " + t("costs.ofTotal", "of total")} />
            <Kpi label={t("costs.overhead", "Study overhead")} value={fmtUsd(Math.max(0, overhead))} foot={t("costs.overheadFoot", "analysis, copilot, translation")} hint={t("costs.overheadHint", "Spend not attributable to a single interview")} />
            <Kpi label={t("costs.perCompleted", "Per completed interview")} value={fmtUsd(data.interview_economics.cost_per_completed_usd, 3)} foot={t("costs.nCompleted", "{{n}} completed", { n: fmtInt(data.interview_economics.completed_interviews) })} />
          </div>

          {data.daily.length > 0 && (
            <Card title={t("costs.dailyTitle", "Daily spend")} sub={t("costs.dailySub", "Interview spend in blue, everything else in grey.")} className="adm-grid">
              <BarChart
                data={data.daily.map((d) => ({ date: d.date, interview: d.interview_cost_usd, overhead: Math.max(0, d.cost_usd - d.interview_cost_usd) }))}
                series={[
                  { key: "interview", label: t("costs.series.interview", "Interviews"), tone: "primary", format: (v) => fmtUsd(v, 2) },
                  { key: "overhead", label: t("costs.series.overhead", "Overhead"), tone: "muted", format: (v) => fmtUsd(v, 2) },
                ]}
              />
            </Card>
          )}

          <EconomicsBlock econ={data.interview_economics} t={t} />

          <div className="adm-grid adm-grid--3">
            <Card title={t("costs.byArea", "By product area")}>
              <StackBar parts={data.by_area.map((a) => ({ label: AREA_LABELS[a.area] ?? a.area, value: a.cost_usd }))} />
            </Card>
            <Card title={t("costs.byModel", "By model")}>
              <DataTable
                rows={data.by_model}
                rowKey={(r) => r.model}
                columns={[
                  { key: "model", label: t("costs.colModel", "Model"), render: (r) => <span className="mono">{r.model}</span> },
                  { key: "calls", label: t("costs.colCalls", "Calls"), num: true, render: (r) => fmtInt(r.calls) },
                  { key: "cost_usd", label: t("costs.colCost", "Cost"), num: true, bar: true, render: (r) => fmtUsd(r.cost_usd) },
                ]}
              />
            </Card>
            <Card title={t("costs.byOperation", "By operation")} sub={t("costs.byOperationSub", "Average is per call.")}>
              <DataTable
                rows={data.by_operation}
                rowKey={(r) => r.operation}
                limit={8}
                defaultSort={{ key: "cost_usd", dir: "desc" }}
                columns={[
                  { key: "operation", label: t("costs.colOperation", "Operation"), sortable: true, render: (r) => <><span className="mono">{r.operation}</span> <span className="adm-pill" style={{ marginLeft: 6 }}>{AREA_LABELS[r.area] ?? r.area}</span></> },
                  { key: "calls", label: t("costs.colCalls", "Calls"), num: true, sortable: true, render: (r) => fmtInt(r.calls) },
                  { key: "avg_cost_usd", label: t("costs.colAvg", "Avg"), num: true, sortable: true, render: (r) => fmtUsd(r.avg_cost_usd, 4) },
                  { key: "cost_usd", label: t("costs.colCost", "Cost"), num: true, sortable: true, bar: true, render: (r) => fmtUsd(r.cost_usd) },
                ]}
              />
            </Card>
          </div>

          <Card
            title={t("costs.byWorkspace", "By workspace")}
            sub={t("costs.byWorkspaceSub", "Click a workspace for its studies and every interview with its own cost. Interview counts exclude demo studies.")}
            right={
              <input
                type="search"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder={t("costs.filterPlaceholder", "Filter by name, email, plan")}
                style={{ padding: "5px 9px", border: "1px solid var(--border)", borderRadius: 6, fontSize: 12.5, minWidth: 220 }}
              />
            }
          >
            <DataTable
              rows={companies}
              rowKey={(r) => r.company_id}
              onRowClick={(r) => onOpenWorkspace(r.company_id)}
              limit={25}
              defaultSort={{ key: "window_cost_usd", dir: "desc" }}
              empty={t("costs.noWorkspaces", "No workspace matches.")}
              columns={[
                {
                  key: "name",
                  label: t("costs.colWorkspace", "Workspace"),
                  sortable: true,
                  render: (r) => (
                    <>
                      <div className="primary">{r.name} {r.has_ever_paid && <span className="adm-pill adm-pill--paid" style={{ marginLeft: 6 }}>{t("costs.paid", "paid")}</span>}</div>
                      <div className="muted">{r.email}</div>
                    </>
                  ),
                },
                { key: "plan_name", label: t("costs.colPlan", "Plan"), sortable: true, render: (r) => r.plan_name ? <span className={`adm-pill${r.plan_is_legacy ? " adm-pill--legacy" : ""}`}>{r.plan_name}</span> : <span className="dim">-</span> },
                { key: "window_interviews", label: days ? t("costs.colInterviewsWindow", "Interviews") : t("costs.colInterviewsAll", "Interviews"), num: true, sortable: true, render: (r) => <>{fmtInt(r.window_interviews)}{days ? <span className="dim"> / {fmtInt(r.total_interviews)}</span> : null}</> },
                { key: "window_cost_per_interview_usd", label: t("costs.colPerInterview", "/ interview"), num: true, sortable: true, render: (r) => fmtUsd(r.window_cost_per_interview_usd, 3) },
                { key: "window_cost_usd", label: days ? t("costs.colSpendWindow", "Spend") : t("costs.colSpendAll", "Spend"), num: true, sortable: true, bar: true, render: (r) => <>{fmtUsd(r.window_cost_usd)}{days ? <span className="dim"> / {fmtUsd(r.total_cost_usd)}</span> : null}</> },
                { key: "last_interview_at", label: t("costs.colLastInterview", "Last interview"), sortable: true, render: (r) => <span className="dim">{fmtRelative(r.last_interview_at)}</span> },
              ]}
            />
          </Card>

          {days > 0 && (
            <p className="adm-toolbar__hint" style={{ marginTop: 4 }}>
              <Delta pct={data.change_pct} invert /> {t("costs.prevNote", "compared with the previous {{n}} days.", { n: days })}
            </p>
          )}
        </>
      )}

      {openWorkspaceId && <WorkspaceCostDrawer client={client} companyId={openWorkspaceId} days={days} onClose={onCloseWorkspace} />}
    </div>
  );
}
