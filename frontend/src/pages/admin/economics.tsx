import { Card, Kpi, StackBar, fmtInt, fmtUsd } from "./ui";

export interface InterviewEconomics {
  completed_interviews: number;
  interviews_with_cost: number;
  total_cost_usd: number;
  cost_per_completed_usd: number;
  per_interview: { avg: number; median: number; p90: number; max: number };
  breakdown: Record<string, number>;
  avg_turns: number;
  avg_audio_minutes: number;
  avg_tts_characters: number;
}

export const BUCKET_LABELS: Record<string, string> = {
  interview_turn: "Claude turns",
  stt: "Speech-to-text",
  tts: "Text-to-speech",
  interview_warmup: "Warmup",
  transcript_cleanup: "Transcript cleanup",
  quality: "Quality pass",
  other: "Other",
};

export function EconomicsBlock({ econ, t }: { econ: InterviewEconomics; t: (k: string, d: string, o?: Record<string, unknown>) => string }) {
  return (
    <div className="adm-grid adm-grid--2">
      <Card
        title={t("costs.econTitle", "What one interview costs")}
        sub={t("costs.econSub", "Fully loaded: every AI call tied to a participant. Study-level work (analysis, copilot, translation) is counted separately as overhead.")}
      >
        <div className="adm-grid adm-grid--kpi" style={{ marginBottom: 16 }}>
          <Kpi label={t("costs.perCompleted", "Per completed interview")} value={fmtUsd(econ.cost_per_completed_usd, 3)} accent foot={t("costs.nCompleted", "{{n}} completed", { n: fmtInt(econ.completed_interviews) })} />
          <Kpi label={t("costs.median", "Median")} value={fmtUsd(econ.per_interview.median, 3)} foot={t("costs.nWithCost", "{{n}} priced, incl. in progress", { n: fmtInt(econ.interviews_with_cost) })} />
          <Kpi label={t("costs.p90", "p90")} value={fmtUsd(econ.per_interview.p90, 3)} foot={t("costs.max", "max {{v}}", { v: fmtUsd(econ.per_interview.max, 3) })} />
        </div>
        <div className="adm-stack-legend" style={{ gridTemplateColumns: "1fr auto", marginBottom: 4 }}>
          <span className="k">{t("costs.avgTurns", "Avg turns")}</span><span className="v">{econ.avg_turns}</span>
          <span className="k">{t("costs.avgAudio", "Avg audio recorded")}</span><span className="v">{econ.avg_audio_minutes} min</span>
          <span className="k">{t("costs.avgTts", "Avg TTS characters")}</span><span className="v">{fmtInt(econ.avg_tts_characters)}</span>
        </div>
      </Card>
      <Card title={t("costs.breakdownTitle", "Inside an interview")} sub={t("costs.breakdownSub", "Where the per-interview dollars go, summed over the window.")}>
        <StackBar parts={Object.entries(econ.breakdown).map(([k, v]) => ({ label: BUCKET_LABELS[k] ?? k, value: v }))} />
      </Card>
    </div>
  );
}
