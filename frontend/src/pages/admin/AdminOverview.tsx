import { useEffect, useState } from "react";
import type { AxiosInstance } from "axios";
import { useTranslation } from "react-i18next";
import { BarChart, Card, Funnel, Kpi, Skeleton, WindowPicker, DataTable, fmtInt, fmtUsd, pct } from "./ui";

interface KpiValue {
  value: number;
  previous: number;
  change_pct: number | null;
}

export interface OverviewReport {
  days: number;
  kpis: {
    signups: KpiValue;
    activated: KpiValue;
    studies_created: KpiValue;
    interviews_completed: KpiValue;
    active_workspaces: KpiValue;
    ai_cost_usd: KpiValue;
    cost_per_interview_usd: KpiValue;
  };
  totals: { users: number; paying_customers: number; interviews_completed: number; ai_cost_usd: number };
  daily: { date: string; signups: number; interviews: number; cost_usd: number }[];
  plan_mix: { label: string; legacy: boolean; count: number }[];
  top_workspaces: { company_id: string; name: string; email: string; interviews: number; cost_usd: number }[];
  funnel: { step: string; count: number }[];
}

export default function AdminOverview({
  client,
  onOpenWorkspace,
}: {
  client: () => AxiosInstance;
  onOpenWorkspace: (companyId: string) => void;
}) {
  const { t } = useTranslation("admin");
  const [days, setDays] = useState(30);
  const [data, setData] = useState<OverviewReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    client()
      .get<OverviewReport>("/admin/overview", { params: { days } })
      .then((r) => { if (!cancelled) setData(r.data); })
      .catch(() => { if (!cancelled) setError(t("overview.loadFailed", "Could not load the overview.")); });
    return () => { cancelled = true; };
  }, [client, days, t]);

  const windowLabel = (d: number) => t("overview.windowDays", "{{n}}d", { n: d });
  const prevLabel = t("overview.vsPrevious", "prev. {{n}}d", { n: days });

  return (
    <div>
      <div className="adm-toolbar">
        <div>
          <h2>{t("overview.title", "Overview")}</h2>
          <div className="adm-toolbar__hint">{t("overview.hint", "Growth and unit economics for the window, compared with the window before it. Demo studies are excluded.")}</div>
        </div>
        <WindowPicker value={days} onChange={setDays} options={[7, 30, 90]} labels={windowLabel} />
      </div>

      {error && <div className="adm-error">{error}</div>}

      {!data ? (
        <div className="adm-grid adm-grid--kpi">
          {Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} h={92} />)}
        </div>
      ) : (
        <>
          <div className="adm-grid adm-grid--kpi">
            <Kpi label={t("overview.kpi.signups", "Signups")} value={fmtInt(data.kpis.signups.value)} previous={fmtInt(data.kpis.signups.previous)} changePct={data.kpis.signups.change_pct} />
            <Kpi
              label={t("overview.kpi.activated", "Onboarded")}
              value={fmtInt(data.kpis.activated.value)}
              previous={fmtInt(data.kpis.activated.previous)}
              changePct={data.kpis.activated.change_pct}
              hint={t("overview.kpi.activatedHint", "Signups in the window that finished onboarding")}
            />
            <Kpi label={t("overview.kpi.studies", "Studies created")} value={fmtInt(data.kpis.studies_created.value)} previous={fmtInt(data.kpis.studies_created.previous)} changePct={data.kpis.studies_created.change_pct} />
            <Kpi label={t("overview.kpi.interviews", "Interviews completed")} value={fmtInt(data.kpis.interviews_completed.value)} previous={fmtInt(data.kpis.interviews_completed.previous)} changePct={data.kpis.interviews_completed.change_pct} accent />
            <Kpi
              label={t("overview.kpi.active", "Active workspaces")}
              value={fmtInt(data.kpis.active_workspaces.value)}
              previous={fmtInt(data.kpis.active_workspaces.previous)}
              changePct={data.kpis.active_workspaces.change_pct}
              hint={t("overview.kpi.activeHint", "Workspaces that completed at least one interview in the window")}
            />
            <Kpi label={t("overview.kpi.cost", "AI spend")} value={fmtUsd(data.kpis.ai_cost_usd.value)} previous={fmtUsd(data.kpis.ai_cost_usd.previous)} changePct={data.kpis.ai_cost_usd.change_pct} invert />
            <Kpi
              label={t("overview.kpi.costPerInterview", "Cost / interview")}
              value={fmtUsd(data.kpis.cost_per_interview_usd.value, 3)}
              previous={fmtUsd(data.kpis.cost_per_interview_usd.previous, 3)}
              changePct={data.kpis.cost_per_interview_usd.change_pct}
              invert
              hint={t("overview.kpi.costPerInterviewHint", "Fully loaded: STT + TTS + Claude turns + warmup + cleanup + quality, divided by completed interviews")}
            />
          </div>

          <div className="adm-grid adm-grid--main">
            <Card title={t("overview.activity", "Daily activity")} right={`${data.daily[0]?.date} → ${data.daily[data.daily.length - 1]?.date}`}>
              <BarChart
                data={data.daily}
                mode="overlay"
                series={[
                  { key: "interviews", label: t("overview.series.interviews", "Interviews"), tone: "primary" },
                  { key: "signups", label: t("overview.series.signups", "Signups"), tone: "secondary" },
                ]}
              />
              <div style={{ height: 14 }} />
              <BarChart
                data={data.daily}
                height={56}
                series={[{ key: "cost_usd", label: t("overview.series.cost", "AI spend"), tone: "muted", format: (v) => fmtUsd(v, 2) }]}
              />
            </Card>

            <div style={{ display: "grid", gap: 14, alignContent: "start" }}>
              <Card title={t("overview.funnel", "Signup cohort funnel")} sub={t("overview.funnelSub", "People who signed up in this window, and how far they got.")}>
                <Funnel
                  steps={data.funnel.map((f) => ({
                    label: t(`overview.funnelStep.${f.step}`, { signed_up: "Signed up", onboarded: "Onboarded", created_study: "Created a study", first_interview: "First interview" }[f.step] ?? f.step),
                    count: f.count,
                  }))}
                />
              </Card>
              <Card title={t("overview.totals", "All time")}>
                <div className="adm-stack-legend" style={{ gridTemplateColumns: "1fr auto" }}>
                  <span className="k">{t("overview.totalUsers", "Users")}</span><span className="v">{fmtInt(data.totals.users)}</span>
                  <span className="k">{t("overview.totalPaying", "Paying customers")}</span><span className="v">{fmtInt(data.totals.paying_customers)} <span className="dim" style={{ color: "var(--text-muted)" }}>({pct(data.totals.paying_customers, data.totals.users)})</span></span>
                  <span className="k">{t("overview.totalInterviews", "Interviews completed")}</span><span className="v">{fmtInt(data.totals.interviews_completed)}</span>
                  <span className="k">{t("overview.totalCost", "AI spend")}</span><span className="v">{fmtUsd(data.totals.ai_cost_usd)}</span>
                </div>
              </Card>
            </div>
          </div>

          <div className="adm-grid adm-grid--2">
            <Card title={t("overview.topWorkspaces", "Most active workspaces")} sub={t("overview.topWorkspacesSub", "By interviews completed in the window. Click a row for the cost breakdown.")}>
              <DataTable
                rows={data.top_workspaces}
                rowKey={(r) => r.company_id}
                onRowClick={(r) => onOpenWorkspace(r.company_id)}
                empty={t("overview.noActivity", "No interviews completed in this window.")}
                columns={[
                  { key: "name", label: t("overview.col.workspace", "Workspace"), render: (r) => <><div className="primary">{r.name}</div><div className="muted">{r.email}</div></> },
                  { key: "interviews", label: t("overview.col.interviews", "Interviews"), num: true, bar: true, render: (r) => fmtInt(r.interviews) },
                  { key: "cost_usd", label: t("overview.col.cost", "AI spend"), num: true, render: (r) => fmtUsd(r.cost_usd) },
                  { key: "per", label: t("overview.col.perInterview", "/ interview"), num: true, value: (r) => (r.interviews ? r.cost_usd / r.interviews : null), render: (r) => fmtUsd(r.interviews ? r.cost_usd / r.interviews : null, 3) },
                ]}
              />
            </Card>
            <Card title={t("overview.planMix", "Plan mix")} sub={t("overview.planMixSub", "Current subscriptions, from the billing table customers are gated on.")}>
              <DataTable
                rows={data.plan_mix}
                rowKey={(r) => r.label}
                columns={[
                  { key: "label", label: t("overview.col.plan", "Plan"), render: (r) => <>{r.label}{r.legacy && <span className="adm-pill adm-pill--legacy" style={{ marginLeft: 8 }}>legacy</span>}</> },
                  { key: "count", label: t("overview.col.workspaces", "Workspaces"), num: true, bar: true, render: (r) => fmtInt(r.count) },
                  { key: "share", label: "%", num: true, value: (r) => r.count, render: (r) => pct(r.count, data.plan_mix.reduce((s, p) => s + p.count, 0)) },
                ]}
              />
            </Card>
          </div>
          <p className="adm-toolbar__hint">{t("overview.prevNote", "Deltas compare with the {{prev}} window.", { prev: prevLabel })}</p>
        </>
      )}
    </div>
  );
}
