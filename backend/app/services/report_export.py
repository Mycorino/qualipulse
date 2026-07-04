"""Render a polished, self-contained HTML research report from a ProjectAnalysis.

The output is a single HTML document with all CSS inlined — no external
requests — designed to read beautifully on screen AND print cleanly to
A4/PDF via the browser's print dialog (a floating no-print toolbar offers
one-click "Save as PDF"). Localised EN/FR keyed off the project language.

Original data stays canonical: this module only *renders* what the analysis
pipeline produced — it never paraphrases quotes or re-scores anything.
"""

import html
import json
from datetime import datetime

# The same 10-colour accent rotation the Analysis tab uses for theme cards,
# so the exported document visually matches the dashboard.
_THEME_ACCENTS = [
    "#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ec4899",
    "#8b5cf6", "#14b8a6", "#f97316", "#06b6d4", "#84cc16",
]

_FREQ_LEVEL = {"all": 4, "most": 3, "some": 2, "few": 1}

_MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]
_MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre"]

_STRINGS = {
    "en": {
        "doc_type": "Research findings report",
        "generated": "Generated",
        "interviews": "completed interviews",
        "confidence": "Confidence",
        "confidence_low": "Low", "confidence_medium": "Medium", "confidence_high": "High",
        "version": "Analysis v{v}",
        "refined": "Researcher-refined",
        "ai_discovery": "AI discovery",
        "segment_filter": "Segment filter",
        "exec_summary": "Executive summary",
        "at_a_glance": "At a glance",
        "stat_participants": "Interviews analysed",
        "stat_themes": "Key themes",
        "stat_jtbd": "Jobs to be done",
        "stat_tensions": "Tensions",
        "stat_recos": "Recommendations",
        "study_design": "Study design",
        "objective": "Research objective",
        "decision": "Decision this informs",
        "target": "Target participants",
        "duration": "Interview length",
        "duration_value": "{m} minutes (target)",
        "field_dates": "Fieldwork window",
        "analysis_lineage": "Analysis version",
        "lineage_refined": "v{v} — refined by the researcher from v{p}",
        "lineage_ai": "v{v} — AI discovery synthesis",
        "themes_title": "Key themes",
        "themes_sub": "Every theme is supported by verbatim quotes from at least two participants. Frequency reflects how widely it appeared across the sample.",
        "freq_all": "Heard from all participants",
        "freq_most": "Heard from most participants",
        "freq_some": "Heard from some participants",
        "freq_few": "Heard from a few participants",
        "disconfirming": "Disconfirming evidence",
        "researcher_note": "Researcher note",
        "annot_confirmed": "Confirmed by researcher",
        "annot_disputed": "Disputed by researcher",
        "annot_needs_evidence": "Flagged: needs more evidence",
        "quote_prompt": "In response to",
        "evidence_map": "Evidence map",
        "evidence_map_sub": "Which participants support each theme. A filled dot means the participant is quoted in that theme.",
        "theme_col": "Theme",
        "jtbd_title": "Jobs to be done",
        "jtbd_sub": "Underlying motivations expressed across interviews, framed as jobs.",
        "insight": "Insight",
        "tensions_title": "Tensions & contradictions",
        "tensions_sub": "Forced choices and contradictions in the data — treat these as open questions, not conclusions.",
        "recos_title": "Recommendations",
        "recos_sub": "Decision-oriented next steps. Each one states what evidence would prove it wrong.",
        "appendix": "Appendix — participants",
        "col_id": "ID", "col_name": "Name", "col_profession": "Profession",
        "col_age": "Age", "col_country": "Country", "col_quality": "Response quality",
        "col_completed": "Completed",
        "quality_low": "Low", "quality_fair": "Fair", "quality_good": "Good", "quality_strong": "Strong",
        "confidence_note": "How to read this confidence level",
        "footer": "Generated with QualiPulse — AI-moderated voice interviews, analysed with full quote traceability.",
        "print_btn": "Print / Save as PDF",
        "anonymous": "Participant",
    },
    "fr": {
        "doc_type": "Rapport de résultats de recherche",
        "generated": "Généré le",
        "interviews": "entretiens terminés",
        "confidence": "Confiance",
        "confidence_low": "Faible", "confidence_medium": "Moyenne", "confidence_high": "Élevée",
        "version": "Analyse v{v}",
        "refined": "Affinée par le chercheur",
        "ai_discovery": "Découverte IA",
        "segment_filter": "Filtre de segment",
        "exec_summary": "Synthèse",
        "at_a_glance": "En un coup d'œil",
        "stat_participants": "Entretiens analysés",
        "stat_themes": "Thèmes clés",
        "stat_jtbd": "Jobs to be done",
        "stat_tensions": "Tensions",
        "stat_recos": "Recommandations",
        "study_design": "Protocole de l'étude",
        "objective": "Objectif de recherche",
        "decision": "Décision éclairée",
        "target": "Participants cibles",
        "duration": "Durée d'entretien",
        "duration_value": "{m} minutes (cible)",
        "field_dates": "Période de terrain",
        "analysis_lineage": "Version d'analyse",
        "lineage_refined": "v{v} — affinée par le chercheur à partir de la v{p}",
        "lineage_ai": "v{v} — synthèse de découverte IA",
        "themes_title": "Thèmes clés",
        "themes_sub": "Chaque thème s'appuie sur des citations verbatim d'au moins deux participants. La fréquence reflète sa présence dans l'échantillon.",
        "freq_all": "Entendu chez tous les participants",
        "freq_most": "Entendu chez la plupart des participants",
        "freq_some": "Entendu chez certains participants",
        "freq_few": "Entendu chez quelques participants",
        "disconfirming": "Preuve contradictoire",
        "researcher_note": "Note du chercheur",
        "annot_confirmed": "Confirmé par le chercheur",
        "annot_disputed": "Contesté par le chercheur",
        "annot_needs_evidence": "Signalé : preuves insuffisantes",
        "quote_prompt": "En réponse à",
        "evidence_map": "Carte des preuves",
        "evidence_map_sub": "Quels participants soutiennent chaque thème. Un point plein signifie que le participant est cité dans ce thème.",
        "theme_col": "Thème",
        "jtbd_title": "Jobs to be done",
        "jtbd_sub": "Motivations sous-jacentes exprimées au fil des entretiens, formulées comme des « jobs ».",
        "insight": "Enseignement",
        "tensions_title": "Tensions & contradictions",
        "tensions_sub": "Choix forcés et contradictions dans les données — à traiter comme des questions ouvertes, pas des conclusions.",
        "recos_title": "Recommandations",
        "recos_sub": "Prochaines étapes orientées décision. Chacune précise ce qui la réfuterait.",
        "appendix": "Annexe — participants",
        "col_id": "ID", "col_name": "Nom", "col_profession": "Profession",
        "col_age": "Âge", "col_country": "Pays", "col_quality": "Qualité des réponses",
        "col_completed": "Terminé le",
        "quality_low": "Faible", "quality_fair": "Passable", "quality_good": "Bonne", "quality_strong": "Solide",
        "confidence_note": "Comment lire ce niveau de confiance",
        "footer": "Généré avec QualiPulse — entretiens vocaux menés par IA, analysés avec traçabilité complète des citations.",
        "print_btn": "Imprimer / Enregistrer en PDF",
        "anonymous": "Participant",
    },
}


def _esc(value) -> str:
    return html.escape(str(value)) if value else ""


def _fmt_date(dt: datetime | None, lang: str) -> str:
    if not dt:
        return "—"
    months = _MONTHS_FR if lang == "fr" else _MONTHS_EN
    return f"{dt.day} {months[dt.month - 1]} {dt.year}"


def _freq_meter(frequency: str, L: dict) -> str:
    level = _FREQ_LEVEL.get((frequency or "").lower(), 0)
    label = L.get(f"freq_{(frequency or '').lower()}", _esc(frequency))
    dots = "".join(
        f'<span class="fdot{" fdot--on" if i < level else ""}"></span>'
        for i in range(4)
    )
    return f'<span class="freq" title="{_esc(label)}">{dots}<span class="freq__label">{_esc(label)}</span></span>'


def _confidence_badge(confidence: str, L: dict) -> str:
    c = (confidence or "").lower()
    label = L.get(f"confidence_{c}", _esc(confidence))
    sep = "&nbsp;:" if L is _STRINGS["fr"] else ":"
    return '<span class="chip chip--conf chip--conf-{}">{}{} {}</span>'.format(
        _esc(c), L["confidence"], sep, label
    )


def render_analysis_report_html(
    project,
    analysis,
    participants: list,
    annotations: list,
    company_name: str = "",
) -> str:
    """Build the full standalone HTML document for one analysis version."""
    lang = "fr" if (project.language or "en").lower().startswith("fr") else "en"
    L = _STRINGS[lang]

    report = json.loads(analysis.report) if analysis.report else {}
    themes = report.get("themes", []) or []
    jtbds = report.get("jobs_to_be_done", []) or []
    tensions = report.get("tensions", []) or []
    recommendations = report.get("recommendations", []) or []

    annot_by_theme = {a.theme_title: a for a in annotations}

    # Stable participant ordering: by completion date, P1..Pn identifiers.
    completed = [p for p in participants if p.status == "completed"]
    completed.sort(key=lambda p: (p.completed_at or p.started_at or datetime.min))
    roster = []  # (identifier, display name, participant)
    for i, p in enumerate(completed):
        name = p.display_name or "{} {}".format(L["anonymous"], i + 1)
        roster.append(("P{}".format(i + 1), name, p))

    filters = None
    if analysis.filters:
        try:
            filters = json.loads(analysis.filters)
        except Exception:
            filters = None

    generated = _fmt_date(analysis.generated_at, lang)
    field_start = min((p.completed_at for p in completed if p.completed_at), default=None)
    field_end = max((p.completed_at for p in completed if p.completed_at), default=None)

    # ── header / cover ────────────────────────────────────────────────────
    refined = analysis.version_label == "researcher_refined"
    version_chip = (
        f'<span class="chip">{L["version"].format(v=analysis.version)} · '
        f'{L["refined"] if refined else L["ai_discovery"]}</span>'
    )
    filter_chip = ""
    if filters and filters.get("filter_by"):
        vals = ", ".join(filters.get("filter_values", []))
        filter_chip = f'<span class="chip chip--filter">{L["segment_filter"]}: {_esc(filters["filter_by"])} = {_esc(vals)}</span>'

    header = f"""
    <header class="cover">
      <div class="cover__brand">
        <span class="cover__logo">QualiPulse</span>
        <span class="cover__doctype">{L["doc_type"]}</span>
      </div>
      <h1 class="cover__title">{_esc(project.name)}</h1>
      <div class="cover__meta">
        <span class="chip chip--strong">{len(completed)} {L["interviews"]}</span>
        {_confidence_badge(report.get("confidence", ""), L)}
        {version_chip}
        {filter_chip}
        <span class="chip chip--ghost">{L["generated"]} {generated}</span>
      </div>
    </header>
    """

    # ── executive summary ─────────────────────────────────────────────────
    exec_summary = f"""
    <section class="summary avoid-break">
      <h2 class="eyebrow">{L["exec_summary"]}</h2>
      <p class="summary__text">{_esc(report.get("summary", ""))}</p>
    </section>
    """

    # ── at a glance ───────────────────────────────────────────────────────
    stats = [
        (len(completed), L["stat_participants"]),
        (len(themes), L["stat_themes"]),
        (len(jtbds), L["stat_jtbd"]),
        (len(tensions), L["stat_tensions"]),
        (len(recommendations), L["stat_recos"]),
    ]
    stat_tiles = "".join(
        f'<div class="stat"><div class="stat__num">{n}</div><div class="stat__label">{lbl}</div></div>'
        for n, lbl in stats
    )
    rationale = report.get("confidence_rationale", "")
    glance = f"""
    <section class="avoid-break">
      <h2 class="eyebrow">{L["at_a_glance"]}</h2>
      <div class="stats">{stat_tiles}</div>
      {f'<p class="rationale"><strong>{L["confidence_note"]}:</strong> {_esc(rationale)}</p>' if rationale else ""}
    </section>
    """

    # ── study design ──────────────────────────────────────────────────────
    design_rows = []
    if project.research_objective:
        design_rows.append((L["objective"], _esc(project.research_objective)))
    if getattr(project, "decision_to_inform", None):
        design_rows.append((L["decision"], _esc(project.decision_to_inform)))
    if getattr(project, "target_customer_description", None):
        design_rows.append((L["target"], _esc(project.target_customer_description)))
    design_rows.append((L["duration"], L["duration_value"].format(m=project.interview_duration_minutes)))
    if field_start and field_end:
        window = _fmt_date(field_start, lang) if field_start.date() == field_end.date() \
            else f"{_fmt_date(field_start, lang)} → {_fmt_date(field_end, lang)}"
        design_rows.append((L["field_dates"], window))
    parent_v = None
    if refined and analysis.parent_version_id:
        parent_v = analysis.version - 1  # display hint; exact parent resolved by caller if needed
    lineage = L["lineage_refined"].format(v=analysis.version, p=parent_v or "?") if refined \
        else L["lineage_ai"].format(v=analysis.version)
    design_rows.append((L["analysis_lineage"], lineage))

    design_html = "".join(
        f'<div class="design__row"><dt>{k}</dt><dd>{v}</dd></div>' for k, v in design_rows
    )
    design = f"""
    <section class="avoid-break">
      <h2 class="eyebrow">{L["study_design"]}</h2>
      <dl class="design">{design_html}</dl>
    </section>
    """

    # ── themes ────────────────────────────────────────────────────────────
    theme_cards = []
    for i, theme in enumerate(themes):
        accent = _THEME_ACCENTS[i % len(_THEME_ACCENTS)]
        quotes_html = ""
        for q in theme.get("quotes", []) or []:
            if isinstance(q, dict):
                text, who = q.get("text", ""), q.get("participant_display_name", "")
                ident = q.get("participant_identifier", "")
                prompt = q.get("question_text", "")
            else:
                text, who, ident, prompt = str(q), "", "", ""
            attribution = " · ".join(x for x in [_esc(ident), _esc(who)] if x)
            prompt_html = f'<div class="quote__prompt">{L["quote_prompt"]}: “{_esc(prompt)}”</div>' if prompt else ""
            quotes_html += f"""
            <blockquote class="quote avoid-break">
              <p>“{_esc(text)}”</p>
              <footer>— {attribution or L["anonymous"]}</footer>
              {prompt_html}
            </blockquote>"""

        disconfirm = theme.get("disconfirming_evidence", "")
        disconfirm_html = f"""
            <div class="callout callout--warn avoid-break">
              <div class="callout__title">{L["disconfirming"]}</div>
              <p>{_esc(disconfirm)}</p>
            </div>""" if disconfirm else ""

        rnote = theme.get("researcher_note", "")
        rnote_html = f"""
            <div class="callout callout--note avoid-break">
              <div class="callout__title">{L["researcher_note"]}</div>
              <p>{_esc(rnote)}</p>
            </div>""" if rnote else ""

        annot = annot_by_theme.get(theme.get("title", ""))
        annot_html = ""
        if annot:
            annot_label = L.get(f"annot_{annot.status}", _esc(annot.status))
            note = f' — {_esc(annot.researcher_note)}' if annot.researcher_note else ""
            annot_html = f'<div class="annot annot--{_esc(annot.status)}">{annot_label}{note}</div>'

        theme_cards.append(f"""
        <article class="theme" style="--accent:{accent}">
          <div class="theme__head avoid-break">
            <span class="theme__num">{i + 1:02d}</span>
            <h3 class="theme__title">{_esc(theme.get("title", ""))}</h3>
            {_freq_meter(theme.get("frequency", ""), L)}
          </div>
          {annot_html}
          <p class="theme__summary">{_esc(theme.get("summary", ""))}</p>
          {quotes_html}
          {disconfirm_html}
          {rnote_html}
        </article>""")

    themes_section = f"""
    <section class="page-break">
      <h2 class="section-title">{L["themes_title"]}</h2>
      <p class="section-sub">{L["themes_sub"]}</p>
      {"".join(theme_cards)}
    </section>
    """ if themes else ""

    # ── evidence map ──────────────────────────────────────────────────────
    evidence_section = ""
    if themes and completed:
        head_cells = "".join(
            '<th title="{}">{}</th>'.format(_esc(name), pid)
            for pid, name, _ in roster
        )
        off_dot = '<span class="dot dot--off"></span>'
        body_rows = ""
        for i, theme in enumerate(themes):
            accent = _THEME_ACCENTS[i % len(_THEME_ACCENTS)]
            on_dot = '<span class="dot" style="background:{}"></span>'.format(accent)
            quoted = {
                q.get("participant_display_name", "")
                for q in (theme.get("quotes", []) or [])
                if isinstance(q, dict)
            }
            cells = "".join(
                "<td>{}</td>".format(on_dot if (p.display_name or "") in quoted else off_dot)
                for _, _, p in roster
            )
            title_cell = _esc(theme.get("title", ""))
            body_rows += '<tr><td class="ev__theme">{}</td>{}</tr>'.format(title_cell, cells)
        legend = " · ".join(
            "<strong>{}</strong> {}".format(pid, _esc(name))
            for pid, name, _ in roster
        )
        evidence_section = f"""
    <section class="avoid-break">
      <h2 class="section-title">{L["evidence_map"]}</h2>
      <p class="section-sub">{L["evidence_map_sub"]}</p>
      <table class="ev">
        <thead><tr><th class="ev__theme">{L["theme_col"]}</th>{head_cells}</tr></thead>
        <tbody>{body_rows}</tbody>
      </table>
      <p class="ev__legend">{legend}</p>
    </section>
    """

    # ── JTBD ──────────────────────────────────────────────────────────────
    jtbd_cards = "".join(f"""
        <article class="jtbd avoid-break">
          <p class="jtbd__job">{_esc(j.get("job", ""))}</p>
          <p class="jtbd__insight"><strong>{L["insight"]}:</strong> {_esc(j.get("insight", ""))}</p>
          {_freq_meter(j.get("frequency", ""), L)}
        </article>""" for j in jtbds)
    jtbd_section = f"""
    <section>
      <h2 class="section-title">{L["jtbd_title"]}</h2>
      <p class="section-sub">{L["jtbd_sub"]}</p>
      <div class="jtbd-grid">{jtbd_cards}</div>
    </section>
    """ if jtbds else ""

    # ── tensions ──────────────────────────────────────────────────────────
    tension_cards = "".join(f"""
        <article class="tension avoid-break">
          <h3 class="tension__label">{_esc(t.get("tension", ""))}</h3>
          <p>{_esc(t.get("detail", ""))}</p>
        </article>""" for t in tensions)
    tensions_section = f"""
    <section>
      <h2 class="section-title">{L["tensions_title"]}</h2>
      <p class="section-sub">{L["tensions_sub"]}</p>
      {tension_cards}
    </section>
    """ if tensions else ""

    # ── recommendations ───────────────────────────────────────────────────
    reco_items = "".join(f"""
        <li class="reco avoid-break"><span class="reco__num">{i + 1}</span><p>{_esc(r)}</p></li>"""
        for i, r in enumerate(recommendations))
    recos_section = f"""
    <section class="avoid-break">
      <h2 class="section-title">{L["recos_title"]}</h2>
      <p class="section-sub">{L["recos_sub"]}</p>
      <ol class="recos">{reco_items}</ol>
    </section>
    """ if recommendations else ""

    # ── appendix ──────────────────────────────────────────────────────────
    roster_rows = ""
    for pid, name, p in roster:
        qkey = "quality_{}".format((p.quality_label or "").lower())
        qlabel = L.get(qkey, _esc(p.quality_label or "—"))
        qclass = "q--{}".format(_esc((p.quality_label or "none").lower()))
        roster_rows += f"""
        <tr>
          <td>{pid}</td>
          <td>{_esc(name)}</td>
          <td>{_esc(p.profession) or "—"}</td>
          <td>{_esc(p.age_range) or "—"}</td>
          <td>{_esc(p.country) or "—"}</td>
          <td><span class="q {qclass}">{qlabel}</span></td>
          <td>{_fmt_date(p.completed_at, lang)}</td>
        </tr>"""
    appendix = f"""
    <section class="page-break">
      <h2 class="section-title">{L["appendix"]}</h2>
      <table class="roster">
        <thead><tr>
          <th>{L["col_id"]}</th><th>{L["col_name"]}</th><th>{L["col_profession"]}</th>
          <th>{L["col_age"]}</th><th>{L["col_country"]}</th><th>{L["col_quality"]}</th><th>{L["col_completed"]}</th>
        </tr></thead>
        <tbody>{roster_rows}</tbody>
      </table>
    </section>
    """ if completed else ""

    title = f"{project.name} — {L['doc_type']}"

    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{_esc(title)}</title>
<style>
:root {{
  --brand: #4369f5; --brand-dark: #1e3fd4; --brand-soft: #f0f4ff;
  --ink: #0d0f1a; --ink-2: #5a6076; --ink-3: #6c7386;
  --line: #e2e4ed; --paper: #ffffff; --wash: #f5f5f7;
  --warn-bg: #fffbeb; --warn-border: #fde68a; --warn-ink: #92400e;
  --ok-bg: #f0fdf4; --ok-ink: #065f46;
  --bad-bg: #fef2f2; --bad-ink: #991b1b;
  --info-bg: #eff6ff; --info-ink: #1e3a8a;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{
  font-family: "Geist", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: var(--ink); background: var(--wash); font-size: 15px; line-height: 1.55;
  letter-spacing: -0.01em;
}}
.sheet {{ max-width: 820px; margin: 0 auto; background: var(--paper); padding: 56px 64px 40px; }}
@media (max-width: 720px) {{ .sheet {{ padding: 32px 20px; }} }}

.cover {{ border-bottom: 1px solid var(--line); padding-bottom: 28px; margin-bottom: 36px; position: relative; }}
.cover::before {{ content: ""; position: absolute; top: -56px; left: -64px; right: -64px; height: 6px;
  background: linear-gradient(90deg, #9bb3ff, var(--brand), var(--brand-dark)); }}
.cover__brand {{ display: flex; align-items: baseline; gap: 12px; margin-bottom: 28px; }}
.cover__logo {{ font-weight: 700; font-size: 1.05rem; color: var(--brand); letter-spacing: -0.02em; }}
.cover__doctype {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.14em; color: var(--ink-3); }}
.cover__title {{ font-size: 2.1rem; line-height: 1.15; font-weight: 700; letter-spacing: -0.03em; margin-bottom: 18px; }}
.cover__meta {{ display: flex; flex-wrap: wrap; gap: 8px; }}

.chip {{ display: inline-block; font-size: 0.75rem; font-weight: 600; padding: 4px 10px;
  border-radius: 999px; background: var(--wash); border: 1px solid var(--line); color: var(--ink-2); }}
.chip--strong {{ background: var(--brand); border-color: var(--brand); color: #fff; }}
.chip--ghost {{ background: transparent; }}
.chip--conf-high {{ background: var(--ok-bg); color: var(--ok-ink); border-color: #bbf7d0; }}
.chip--conf-medium {{ background: var(--warn-bg); color: var(--warn-ink); border-color: var(--warn-border); }}
.chip--conf-low {{ background: var(--bad-bg); color: var(--bad-ink); border-color: #fecaca; }}
.chip--filter {{ background: var(--info-bg); color: var(--info-ink); border-color: #bfdbfe; }}

.eyebrow {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.14em;
  color: var(--brand); font-weight: 700; margin-bottom: 12px; }}
section {{ margin-bottom: 40px; }}

.summary {{ background: var(--brand-soft); border-left: 4px solid var(--brand);
  padding: 24px 28px; border-radius: 0 12px 12px 0; }}
.summary__text {{ font-size: 1.15rem; line-height: 1.6; font-weight: 500; letter-spacing: -0.015em; }}

.stats {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }}
@media (max-width: 720px) {{ .stats {{ grid-template-columns: repeat(2, 1fr); }} }}
.stat {{ border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; text-align: center; }}
.stat__num {{ font-size: 1.7rem; font-weight: 700; letter-spacing: -0.03em; color: var(--brand-dark); }}
.stat__label {{ font-size: 0.72rem; color: var(--ink-3); margin-top: 2px; }}
.rationale {{ margin-top: 14px; font-size: 0.85rem; color: var(--ink-2); background: var(--wash);
  border-radius: 10px; padding: 12px 16px; }}

.design {{ border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }}
.design__row {{ display: grid; grid-template-columns: 220px 1fr; }}
.design__row + .design__row {{ border-top: 1px solid var(--line); }}
.design__row dt {{ padding: 12px 18px; background: var(--wash); font-size: 0.78rem; font-weight: 600;
  color: var(--ink-2); text-transform: uppercase; letter-spacing: 0.05em; }}
.design__row dd {{ padding: 12px 18px; font-size: 0.9rem; }}
@media (max-width: 720px) {{ .design__row {{ grid-template-columns: 1fr; }} .design__row dd {{ padding-top: 0; }} }}

.section-title {{ font-size: 1.45rem; font-weight: 700; letter-spacing: -0.025em; margin-bottom: 6px; }}
.section-sub {{ font-size: 0.88rem; color: var(--ink-3); margin-bottom: 22px; max-width: 60ch; }}

.theme {{ border: 1px solid var(--line); border-left: 4px solid var(--accent); border-radius: 0 14px 14px 0;
  padding: 22px 26px; margin-bottom: 22px; }}
.theme__head {{ display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }}
.theme__num {{ font-size: 0.8rem; font-weight: 700; color: var(--accent); }}
.theme__title {{ font-size: 1.12rem; font-weight: 700; letter-spacing: -0.02em; flex: 1; }}
.theme__summary {{ font-size: 0.92rem; color: var(--ink-2); margin-bottom: 14px; }}

.freq {{ display: inline-flex; align-items: center; gap: 4px; }}
.fdot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--line); display: inline-block; }}
.fdot--on {{ background: var(--accent, var(--brand)); }}
.freq__label {{ font-size: 0.72rem; color: var(--ink-3); margin-left: 4px; }}

.quote {{ border-left: 3px solid var(--line); padding: 8px 0 8px 18px; margin: 12px 0 12px 6px; }}
.quote p {{ font-size: 0.95rem; font-style: italic; color: var(--ink); }}
.quote footer {{ font-size: 0.78rem; color: var(--ink-3); margin-top: 6px; font-weight: 600; }}
.quote__prompt {{ font-size: 0.74rem; color: var(--ink-3); margin-top: 3px; }}

.callout {{ border-radius: 10px; padding: 14px 18px; margin-top: 14px; font-size: 0.88rem; }}
.callout__title {{ font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px; }}
.callout--warn {{ background: var(--warn-bg); border: 1px solid var(--warn-border); color: var(--warn-ink); }}
.callout--note {{ background: var(--info-bg); border: 1px solid #bfdbfe; color: var(--info-ink); }}

.annot {{ display: inline-block; font-size: 0.76rem; font-weight: 600; padding: 4px 12px;
  border-radius: 999px; margin-bottom: 10px; }}
.annot--confirmed {{ background: var(--ok-bg); color: var(--ok-ink); }}
.annot--disputed {{ background: var(--bad-bg); color: var(--bad-ink); }}
.annot--needs_evidence {{ background: var(--warn-bg); color: var(--warn-ink); }}

.ev {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
.ev th, .ev td {{ border: 1px solid var(--line); padding: 8px 10px; text-align: center; }}
.ev th {{ background: var(--wash); font-size: 0.74rem; }}
.ev__theme {{ text-align: left !important; font-weight: 600; max-width: 300px; }}
.dot {{ display: inline-block; width: 11px; height: 11px; border-radius: 50%; }}
.dot--off {{ background: var(--line); opacity: 0.45; width: 7px; height: 7px; }}
.ev__legend {{ font-size: 0.74rem; color: var(--ink-3); margin-top: 10px; }}

.jtbd-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
@media (max-width: 720px) {{ .jtbd-grid {{ grid-template-columns: 1fr; }} }}
.jtbd {{ border: 1px solid var(--line); border-top: 4px solid #f59e0b; border-radius: 12px; padding: 18px 20px; }}
.jtbd__job {{ font-weight: 600; font-size: 0.95rem; margin-bottom: 8px; letter-spacing: -0.01em; }}
.jtbd__insight {{ font-size: 0.85rem; color: var(--ink-2); margin-bottom: 10px; }}
.jtbd .fdot--on {{ background: #f59e0b; }}

.tension {{ border: 1px solid var(--line); border-left: 4px solid #ef4444; border-radius: 0 12px 12px 0;
  padding: 16px 20px; margin-bottom: 14px; }}
.tension__label {{ font-size: 0.98rem; font-weight: 700; margin-bottom: 6px; }}
.tension p {{ font-size: 0.88rem; color: var(--ink-2); }}

.recos {{ list-style: none; }}
.reco {{ display: flex; gap: 16px; align-items: flex-start; border: 1px solid var(--line);
  border-radius: 12px; padding: 16px 20px; margin-bottom: 12px; }}
.reco__num {{ flex: 0 0 auto; width: 30px; height: 30px; border-radius: 50%; background: var(--brand);
  color: #fff; font-weight: 700; font-size: 0.9rem; display: flex; align-items: center; justify-content: center; }}
.reco p {{ font-size: 0.92rem; padding-top: 3px; }}

.roster {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
.roster th, .roster td {{ border: 1px solid var(--line); padding: 8px 12px; text-align: left; }}
.roster th {{ background: var(--wash); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--ink-2); }}
.q {{ font-size: 0.74rem; font-weight: 600; padding: 2px 10px; border-radius: 999px; }}
.q--strong, .q--good {{ background: var(--ok-bg); color: var(--ok-ink); }}
.q--fair {{ background: var(--warn-bg); color: var(--warn-ink); }}
.q--low {{ background: var(--bad-bg); color: var(--bad-ink); }}
.q--none {{ background: var(--wash); color: var(--ink-3); }}

.doc-footer {{ border-top: 1px solid var(--line); margin-top: 48px; padding-top: 18px;
  font-size: 0.76rem; color: var(--ink-3); display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
.doc-footer strong {{ color: var(--brand); }}

.toolbar {{ position: fixed; top: 18px; right: 18px; z-index: 10; }}
.toolbar button {{ font: inherit; font-size: 0.82rem; font-weight: 600; color: #fff; background: var(--brand);
  border: 0; border-radius: 999px; padding: 10px 18px; cursor: pointer; box-shadow: 0 4px 16px rgba(13,15,26,0.18); }}
.toolbar button:hover {{ background: var(--brand-dark); }}

.avoid-break {{ break-inside: avoid; page-break-inside: avoid; }}
@media print {{
  body {{ background: #fff; }}
  .sheet {{ max-width: none; padding: 0; }}
  .toolbar {{ display: none; }}
  .cover::before {{ left: 0; right: 0; top: 0; }}
  .cover {{ padding-top: 18px; }}
  section {{ margin-bottom: 28px; }}
  .page-break {{ break-before: page; page-break-before: always; }}
  @page {{ size: A4; margin: 16mm 14mm; }}
}}
</style>
</head>
<body>
<div class="toolbar"><button onclick="window.print()">{L["print_btn"]}</button></div>
<div class="sheet">
{header}
{exec_summary}
{glance}
{design}
{themes_section}
{evidence_section}
{jtbd_section}
{tensions_section}
{recos_section}
{appendix}
<footer class="doc-footer">
  <span><strong>QualiPulse</strong> · {_esc(company_name)}</span>
  <span>{L["footer"]}</span>
</footer>
</div>
</body>
</html>"""
