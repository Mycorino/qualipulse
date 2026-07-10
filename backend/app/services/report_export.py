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
        "quote_unverified": "⚠ Not found verbatim in the transcript — verify before citing.",
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
        "quote_unverified": "⚠ Introuvable telle quelle dans le verbatim — à vérifier avant citation.",
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
    include_appendix: bool = True,
) -> str:
    """Build the full standalone HTML document for one analysis version.

    ``include_appendix=False`` is the public-share variant: the participant
    roster (demographics + quality labels) is stripped.
    """
    # The analysis body is written in the owning company's preferred_language
    # (services/analysis.py) — the report chrome must match the body, not the
    # interview language, or an EN researcher running a FR study gets French
    # labels around English analysis text.
    company_lang = getattr(getattr(project, "company", None), "preferred_language", None)
    lang = "fr" if (company_lang or project.language or "en").lower().startswith("fr") else "en"
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
            # Only flag when verification explicitly failed. Absent `verified`
            # (legacy reports / fixtures generated before quote-checking) shows
            # no marker so we never imply a clean quote is suspect.
            unverified_html = (
                f'<div class="quote__unverified">{L["quote_unverified"]}</div>'
                if isinstance(q, dict) and q.get("verified") is False
                else ""
            )
            quotes_html += f"""
            <blockquote class="quote avoid-break">
              <p>“{_esc(text)}”</p>
              <footer>— {attribution or L["anonymous"]}</footer>
              {prompt_html}
              {unverified_html}
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
    """ if (completed and include_appendix) else ""

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
.quote__unverified {{ font-size: 0.72rem; color: #b45309; margin-top: 4px; font-weight: 600; }}

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


# ═══════════════════════════════════════════════════════════════════════════
# Decision memo — cross-study synthesis document
# ═══════════════════════════════════════════════════════════════════════════

_MEMO_STRINGS = {
    "en": {
        "doc_type": "Decision memo",
        "generated": "Generated",
        "studies": "studies",
        "confidence": "Confidence",
        "confidence_low": "Low", "confidence_medium": "Medium", "confidence_high": "High",
        "decision": "Decision under consideration",
        "verdict": "Verdict",
        "summary": "Executive summary",
        "findings": "Key findings across studies",
        "findings_sub": "Every finding names the studies that support it. Strength reflects cross-study corroboration, not enthusiasm.",
        "strength_strong": "Strong evidence",
        "strength_moderate": "Moderate evidence",
        "strength_weak": "Weak evidence",
        "evidence": "Most convincing evidence",
        "conflicts": "Where the studies disagree",
        "conflicts_sub": "Treat these as open questions, not noise — disagreement between studies is information.",
        "gaps": "What we still don't know",
        "recos": "Recommendations",
        "recos_sub": "Decision-oriented next steps. Each one states what evidence would prove it wrong.",
        "included": "Studies included",
        "col_study": "Study", "col_n": "Interviews", "col_conf": "Confidence",
        "col_date": "Analysed", "col_mixed": "Mixed methods",
        "confidence_note": "How to read this confidence level",
        "footer": "Generated with QualiPulse — synthesised from per-study analyses with full quote traceability.",
        "print_btn": "Print / Save as PDF",
        "yes": "Yes", "no": "—",
    },
    "fr": {
        "doc_type": "Mémo de décision",
        "generated": "Généré le",
        "studies": "études",
        "confidence": "Confiance",
        "confidence_low": "Faible", "confidence_medium": "Moyenne", "confidence_high": "Élevée",
        "decision": "Décision à éclairer",
        "verdict": "Verdict",
        "summary": "Synthèse",
        "findings": "Enseignements clés transverses",
        "findings_sub": "Chaque enseignement nomme les études qui le soutiennent. La force reflète la corroboration entre études.",
        "strength_strong": "Preuves solides",
        "strength_moderate": "Preuves modérées",
        "strength_weak": "Preuves faibles",
        "evidence": "Preuve la plus convaincante",
        "conflicts": "Là où les études divergent",
        "conflicts_sub": "À traiter comme des questions ouvertes — un désaccord entre études est une information.",
        "gaps": "Ce que nous ne savons toujours pas",
        "recos": "Recommandations",
        "recos_sub": "Prochaines étapes orientées décision. Chacune précise ce qui la réfuterait.",
        "included": "Études incluses",
        "col_study": "Étude", "col_n": "Entretiens", "col_conf": "Confiance",
        "col_date": "Analysée le", "col_mixed": "Méthodes mixtes",
        "confidence_note": "Comment lire ce niveau de confiance",
        "footer": "Généré avec QualiPulse — synthétisé à partir des analyses de chaque étude, avec traçabilité complète des citations.",
        "print_btn": "Imprimer / Enregistrer en PDF",
        "yes": "Oui", "no": "—",
    },
}

_STRENGTH_LEVEL = {"strong": 3, "moderate": 2, "weak": 1}

_MEMO_CSS = """
:root {
  --brand: #4369f5; --brand-dark: #1e3fd4; --brand-soft: #f0f4ff;
  --ink: #0d0f1a; --ink-2: #5a6076; --ink-3: #6c7386;
  --line: #e2e4ed; --paper: #ffffff; --wash: #f5f5f7;
  --warn-bg: #fffbeb; --warn-border: #fde68a; --warn-ink: #92400e;
  --ok-bg: #f0fdf4; --ok-ink: #065f46;
  --bad-bg: #fef2f2; --bad-ink: #991b1b;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Geist", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: var(--ink); background: var(--wash); font-size: 15px; line-height: 1.55; letter-spacing: -0.01em; }
.sheet { max-width: 820px; margin: 0 auto; background: var(--paper); padding: 56px 64px 40px; }
@media (max-width: 720px) { .sheet { padding: 32px 20px; } }
.cover { border-bottom: 1px solid var(--line); padding-bottom: 28px; margin-bottom: 36px; position: relative; }
.cover::before { content: ""; position: absolute; top: -56px; left: -64px; right: -64px; height: 6px;
  background: linear-gradient(90deg, #9bb3ff, var(--brand), var(--brand-dark)); }
.cover__brand { display: flex; align-items: baseline; gap: 12px; margin-bottom: 28px; }
.cover__logo { font-weight: 700; font-size: 1.05rem; color: var(--brand); letter-spacing: -0.02em; }
.cover__doctype { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.14em; color: var(--ink-3); }
.cover__title { font-size: 2.1rem; line-height: 1.15; font-weight: 700; letter-spacing: -0.03em; margin-bottom: 18px; }
.cover__meta { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { display: inline-block; font-size: 0.75rem; font-weight: 600; padding: 4px 10px;
  border-radius: 999px; background: var(--wash); border: 1px solid var(--line); color: var(--ink-2); }
.chip--strong { background: var(--brand); border-color: var(--brand); color: #fff; }
.chip--ghost { background: transparent; }
.chip--conf-high { background: var(--ok-bg); color: var(--ok-ink); border-color: #bbf7d0; }
.chip--conf-medium { background: var(--warn-bg); color: var(--warn-ink); border-color: var(--warn-border); }
.chip--conf-low { background: var(--bad-bg); color: var(--bad-ink); border-color: #fecaca; }
.eyebrow { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.14em;
  color: var(--brand); font-weight: 700; margin-bottom: 12px; }
section { margin-bottom: 40px; }
.decision-q { font-size: 1.05rem; font-weight: 600; color: var(--ink-2); }
.verdict { background: var(--brand-soft); border-left: 4px solid var(--brand);
  padding: 24px 28px; border-radius: 0 12px 12px 0; }
.verdict p { font-size: 1.15rem; line-height: 1.6; font-weight: 500; letter-spacing: -0.015em; }
.summary-text { font-size: 0.98rem; color: var(--ink-2); max-width: 68ch; }
.rationale { margin-top: 14px; font-size: 0.85rem; color: var(--ink-2); background: var(--wash);
  border-radius: 10px; padding: 12px 16px; }
.section-title { font-size: 1.45rem; font-weight: 700; letter-spacing: -0.025em; margin-bottom: 6px; }
.section-sub { font-size: 0.88rem; color: var(--ink-3); margin-bottom: 22px; max-width: 60ch; }
.finding { border: 1px solid var(--line); border-left: 4px solid var(--brand); border-radius: 0 14px 14px 0;
  padding: 22px 26px; margin-bottom: 18px; }
.finding__head { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.finding__num { font-size: 0.8rem; font-weight: 700; color: var(--brand); }
.finding__title { font-size: 1.08rem; font-weight: 700; letter-spacing: -0.02em; flex: 1; }
.strength { display: inline-flex; align-items: center; gap: 4px; }
.sdot { width: 8px; height: 8px; border-radius: 50%; background: var(--line); display: inline-block; }
.sdot--on { background: var(--brand); }
.strength__label { font-size: 0.72rem; color: var(--ink-3); margin-left: 4px; }
.finding__detail { font-size: 0.92rem; color: var(--ink-2); margin-bottom: 12px; }
.finding__studies { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.finding__evidence { border-left: 3px solid var(--line); padding: 8px 0 8px 18px; margin-left: 6px; }
.finding__evidence .lbl { font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--ink-3); display: block; margin-bottom: 3px; }
.finding__evidence p { font-size: 0.92rem; font-style: italic; }
.conflict { border: 1px solid var(--line); border-left: 4px solid #ef4444; border-radius: 0 12px 12px 0;
  padding: 16px 20px; margin-bottom: 14px; }
.conflict h3 { font-size: 0.98rem; font-weight: 700; margin-bottom: 6px; }
.conflict p { font-size: 0.88rem; color: var(--ink-2); }
.gaps { list-style: none; }
.gaps li { background: var(--warn-bg); border: 1px solid var(--warn-border); color: var(--warn-ink);
  border-radius: 10px; padding: 12px 18px; margin-bottom: 10px; font-size: 0.9rem; }
.recos { list-style: none; }
.reco { display: flex; gap: 16px; align-items: flex-start; border: 1px solid var(--line);
  border-radius: 12px; padding: 16px 20px; margin-bottom: 12px; }
.reco__num { flex: 0 0 auto; width: 30px; height: 30px; border-radius: 50%; background: var(--brand);
  color: #fff; font-weight: 700; font-size: 0.9rem; display: flex; align-items: center; justify-content: center; }
.reco p { font-size: 0.92rem; padding-top: 3px; }
.included { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.included th, .included td { border: 1px solid var(--line); padding: 8px 12px; text-align: left; }
.included th { background: var(--wash); font-size: 0.72rem; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--ink-2); }
.doc-footer { border-top: 1px solid var(--line); margin-top: 48px; padding-top: 18px;
  font-size: 0.76rem; color: var(--ink-3); display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.doc-footer strong { color: var(--brand); }
.toolbar { position: fixed; top: 18px; right: 18px; z-index: 10; }
.toolbar button { font: inherit; font-size: 0.82rem; font-weight: 600; color: #fff; background: var(--brand);
  border: 0; border-radius: 999px; padding: 10px 18px; cursor: pointer; box-shadow: 0 4px 16px rgba(13,15,26,0.18); }
.toolbar button:hover { background: var(--brand-dark); }
.avoid-break { break-inside: avoid; page-break-inside: avoid; }
@media print {
  body { background: #fff; }
  .sheet { max-width: none; padding: 0; }
  .toolbar { display: none; }
  .cover::before { left: 0; right: 0; top: 0; }
  .cover { padding-top: 18px; }
  section { margin-bottom: 28px; }
  @page { size: A4; margin: 16mm 14mm; }
}
"""


def _strength_meter(strength: str, L: dict) -> str:
    level = _STRENGTH_LEVEL.get((strength or "").lower(), 0)
    label = L.get("strength_{}".format((strength or "").lower()), _esc(strength))
    dots = "".join(
        '<span class="sdot{}"></span>'.format(" sdot--on" if i < level else "")
        for i in range(3)
    )
    return f'<span class="strength" title="{_esc(label)}">{dots}<span class="strength__label">{_esc(label)}</span></span>'


def render_decision_memo_html(synthesis, studies_meta: list, company_name: str = "") -> str:
    """Standalone print-ready HTML for one CrossStudySynthesis decision memo.

    ``studies_meta`` — list of dicts: name, participant_count, confidence,
    generated_at, has_mixed_methods (built by the router from live rows).
    """
    lang = "fr" if (synthesis.language or "en").lower().startswith("fr") else "en"
    L = _MEMO_STRINGS[lang]

    report = json.loads(synthesis.report) if synthesis.report else {}
    findings = report.get("key_findings", []) or []
    conflicts = report.get("conflicts", []) or []
    gaps = report.get("gaps", []) or []
    recommendations = report.get("recommendations", []) or []

    conf = (report.get("confidence", "") or "").lower()
    conf_label = L.get("confidence_{}".format(conf), _esc(report.get("confidence", "")))
    sep = "&nbsp;:" if lang == "fr" else ":"

    header = f"""
    <header class="cover">
      <div class="cover__brand">
        <span class="cover__logo">QualiPulse</span>
        <span class="cover__doctype">{L["doc_type"]}</span>
      </div>
      <h1 class="cover__title">{_esc(synthesis.name)}</h1>
      <div class="cover__meta">
        <span class="chip chip--strong">{len(studies_meta)} {L["studies"]}</span>
        <span class="chip chip--conf-{_esc(conf)}">{L["confidence"]}{sep} {conf_label}</span>
        <span class="chip chip--ghost">{L["generated"]} {_fmt_date(synthesis.generated_at, lang)}</span>
      </div>
    </header>
    """

    decision_section = f"""
    <section class="avoid-break">
      <h2 class="eyebrow">{L["decision"]}</h2>
      <p class="decision-q">{_esc(report.get("decision", synthesis.decision_question or ""))}</p>
    </section>
    """

    rationale = report.get("confidence_rationale", "")
    verdict_section = f"""
    <section class="avoid-break">
      <h2 class="eyebrow">{L["verdict"]}</h2>
      <div class="verdict"><p>{_esc(report.get("verdict", ""))}</p></div>
      {f'<p class="rationale"><strong>{L["confidence_note"]}:</strong> {_esc(rationale)}</p>' if rationale else ""}
    </section>
    """

    summary_section = f"""
    <section class="avoid-break">
      <h2 class="eyebrow">{L["summary"]}</h2>
      <p class="summary-text">{_esc(report.get("summary", ""))}</p>
    </section>
    """ if report.get("summary") else ""

    finding_cards = []
    for i, f in enumerate(findings):
        chips = "".join(
            '<span class="chip">{}</span>'.format(_esc(s))
            for s in (f.get("supporting_studies", []) or [])
        )
        evidence = f.get("evidence", "")
        evidence_html = f"""
          <div class="finding__evidence avoid-break">
            <span class="lbl">{L["evidence"]}</span>
            <p>{_esc(evidence)}</p>
          </div>""" if evidence else ""
        finding_cards.append(f"""
        <article class="finding avoid-break">
          <div class="finding__head">
            <span class="finding__num">{i + 1:02d}</span>
            <h3 class="finding__title">{_esc(f.get("finding", ""))}</h3>
            {_strength_meter(f.get("strength", ""), L)}
          </div>
          <p class="finding__detail">{_esc(f.get("detail", ""))}</p>
          <div class="finding__studies">{chips}</div>
          {evidence_html}
        </article>""")
    findings_section = f"""
    <section>
      <h2 class="section-title">{L["findings"]}</h2>
      <p class="section-sub">{L["findings_sub"]}</p>
      {"".join(finding_cards)}
    </section>
    """ if findings else ""

    conflict_cards = "".join(f"""
        <article class="conflict avoid-break">
          <h3>{_esc(c.get("topic", ""))}</h3>
          <p>{_esc(c.get("detail", ""))}</p>
        </article>""" for c in conflicts)
    conflicts_section = f"""
    <section>
      <h2 class="section-title">{L["conflicts"]}</h2>
      <p class="section-sub">{L["conflicts_sub"]}</p>
      {conflict_cards}
    </section>
    """ if conflicts else ""

    gap_items = "".join(f'<li class="avoid-break">{_esc(g)}</li>' for g in gaps)
    gaps_section = f"""
    <section class="avoid-break">
      <h2 class="section-title">{L["gaps"]}</h2>
      <ul class="gaps">{gap_items}</ul>
    </section>
    """ if gaps else ""

    reco_items = "".join(f"""
        <li class="reco avoid-break"><span class="reco__num">{i + 1}</span><p>{_esc(r)}</p></li>"""
        for i, r in enumerate(recommendations))
    recos_section = f"""
    <section class="avoid-break">
      <h2 class="section-title">{L["recos"]}</h2>
      <p class="section-sub">{L["recos_sub"]}</p>
      <ol class="recos">{reco_items}</ol>
    </section>
    """ if recommendations else ""

    included_rows = ""
    for m in studies_meta:
        m_conf = (m.get("confidence") or "").lower()
        m_conf_label = L.get("confidence_{}".format(m_conf), "—") if m_conf else "—"
        included_rows += f"""
        <tr>
          <td>{_esc(m.get("name", ""))}</td>
          <td>{m.get("participant_count") if m.get("participant_count") is not None else "—"}</td>
          <td>{m_conf_label}</td>
          <td>{_fmt_date(m.get("generated_at"), lang)}</td>
          <td>{L["yes"] if m.get("has_mixed_methods") else L["no"]}</td>
        </tr>"""
    included_section = f"""
    <section class="avoid-break">
      <h2 class="section-title">{L["included"]}</h2>
      <table class="included">
        <thead><tr>
          <th>{L["col_study"]}</th><th>{L["col_n"]}</th><th>{L["col_conf"]}</th>
          <th>{L["col_date"]}</th><th>{L["col_mixed"]}</th>
        </tr></thead>
        <tbody>{included_rows}</tbody>
      </table>
    </section>
    """ if studies_meta else ""

    title = f"{synthesis.name} — {L['doc_type']}"

    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{_esc(title)}</title>
<style>{_MEMO_CSS}</style>
</head>
<body>
<div class="toolbar"><button onclick="window.print()">{L["print_btn"]}</button></div>
<div class="sheet">
{header}
{decision_section}
{verdict_section}
{summary_section}
{findings_section}
{conflicts_section}
{gaps_section}
{recos_section}
{included_section}
<footer class="doc-footer">
  <span><strong>QualiPulse</strong> · {_esc(company_name)}</span>
  <span>{L["footer"]}</span>
</footer>
</div>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════
# Mixed-methods study report — Quantified Themes as a research-grade document
# ═══════════════════════════════════════════════════════════════════════════

_STUDY_STRINGS = {
    "en": {
        "doc_type": "Mixed-methods research report",
        "generated": "Generated",
        "version": "Report v{v}",
        "responses": "survey responses",
        "interviews": "interviews",
        "sec_essentials": "The essentials",
        "sec_evidence": "The evidence at a glance",
        "sec_theme": "Theme {i} · What the evidence says",
        "sec_methodology": "Methodology, limits & evidence index",
        "verdict_label": "Verdict",
        "stat_responses": "Completed survey responses",
        "stat_interviews": "Completed interviews",
        "stat_themes": "Quantified themes",
        "stat_surveys": "Survey instruments",
        "stat_validated": "Themes validated by respondents",
        "conf_directional": "Directional",
        "conf_supported": "Supported",
        "conf_strong": "Strong",
        "why_strong": "Why “strong”: {parts} — meets the n≥100, p<0.01-equivalent bar of the methodology contract.",
        "why_supported": "Why “supported”: {parts} — quantitative signal and interviews agree through independent routes.",
        "why_directional": "Why “directional”: {parts} — below inference thresholds or resting on a single method. Treat as a hypothesis to test next.",
        "why_survey_n": "n={n} survey responses",
        "why_segment": "segment “{s}”",
        "why_lift": "{lift}× over-index",
        "why_interviews": "corroborated in {x} interviews",
        "why_survey_only": "survey signal only",
        "survey_signal": "Survey signal",
        "interview_evidence": "Interview evidence · {x}",
        "segments_mentioned": "Raised by: {s}",
        "validation_label": "Respondent validation",
        "validation_agree_pct": "{pct}% agree (95% CI {lo}–{hi}, n={n})",
        "validation_agree_counts": "{agree} of {n} respondents agree — below n=30, raw counts only",
        "validation_awaiting": "Awaiting validation responses for this theme.",
        "reco_product": "Product action",
        "reco_marketing": "Marketing action",
        "reco_next_research": "Next research step",
        "chart_n": "n={n}",
        "chart_no_pct": "Sub-threshold group (n<30) — raw counts, no percentages.",
        "chart_mean": "mean {m}",
        "chart_nps": "NPS {score} · {p} promoters / {pa} passives / {d} detractors",
        "chart_open_text": "{n} open-text answers — read them in the survey dashboard.",
        "methodology_note": "How this report was produced",
        "contract_title": "Methodology contract",
        "contract_items": [
            "No percentage is shown below n=30; sub-threshold groups are reported as raw counts. Confidence intervals are Wilson 95%.",
            "A theme is “supported” when quantitative signal and interviews agree through independent routes (n≥30 + meaningful effect); “strong” requires n≥100 and a p<0.01-equivalent effect; anything less is “directional”.",
            "Every anchor quote is verified post-generation as a verbatim substring of a real interview transcript; unverifiable quotes are stripped automatically.",
            "Analysis generated by AI (Claude) from survey aggregates and interview transcripts, reviewed by the research team before distribution.",
        ],
        "evidence_index": "Evidence index",
        "idx_surveys": "Surveys",
        "idx_interviews": "Interviews",
        "col_instrument": "Instrument", "col_status": "Status",
        "col_questions": "Questions", "col_completed": "Completed",
        "col_id": "ID", "col_name": "Participant", "col_profession": "Profession",
        "col_country": "Country", "col_turns": "Turns",
        "anonymous": "Participant",
        "footer": "Generated with QualiPulse — survey signal and interview evidence combined with full quote traceability.",
        "print_btn": "Print / Save as PDF",
    },
    "fr": {
        "doc_type": "Rapport de recherche mixte",
        "generated": "Généré le",
        "version": "Rapport v{v}",
        "responses": "réponses au sondage",
        "interviews": "entretiens",
        "sec_essentials": "L'essentiel",
        "sec_evidence": "La preuve en un coup d'œil",
        "sec_theme": "Thème {i} · Ce que dit la preuve",
        "sec_methodology": "Méthodologie, limites & index des preuves",
        "verdict_label": "Verdict",
        "stat_responses": "Réponses complètes au sondage",
        "stat_interviews": "Entretiens terminés",
        "stat_themes": "Thèmes quantifiés",
        "stat_surveys": "Questionnaires",
        "stat_validated": "Thèmes validés par les répondants",
        "conf_directional": "Indicatif",
        "conf_supported": "Étayé",
        "conf_strong": "Solide",
        "why_strong": "Pourquoi « solide » : {parts} — atteint le seuil n≥100 et un effet équivalent p<0,01 du contrat méthodologique.",
        "why_supported": "Pourquoi « étayé » : {parts} — le signal quantitatif et les entretiens concordent par des voies indépendantes.",
        "why_directional": "Pourquoi « indicatif » : {parts} — sous les seuils d'inférence ou fondé sur une seule méthode. À traiter comme une hypothèse à tester.",
        "why_survey_n": "n={n} réponses au sondage",
        "why_segment": "segment « {s} »",
        "why_lift": "sur-représentation ×{lift}",
        "why_interviews": "corroboré dans {x} entretiens",
        "why_survey_only": "signal du sondage uniquement",
        "survey_signal": "Signal du questionnaire",
        "interview_evidence": "Preuve d'entretien · {x}",
        "segments_mentioned": "Évoqué par : {s}",
        "validation_label": "Validation par les répondants",
        "validation_agree_pct": "{pct}% d'accord (IC 95% {lo}–{hi}, n={n})",
        "validation_agree_counts": "{agree} répondants sur {n} d'accord — sous n=30, effectifs bruts uniquement",
        "validation_awaiting": "En attente des réponses de validation pour ce thème.",
        "reco_product": "Action produit",
        "reco_marketing": "Action marketing",
        "reco_next_research": "Prochaine étape de recherche",
        "chart_n": "n={n}",
        "chart_no_pct": "Groupe sous le seuil (n<30) — effectifs bruts, pas de pourcentages.",
        "chart_mean": "moyenne {m}",
        "chart_nps": "NPS {score} · {p} promoteurs / {pa} passifs / {d} détracteurs",
        "chart_open_text": "{n} réponses libres — à lire dans le tableau de bord du questionnaire.",
        "methodology_note": "Comment ce rapport a été produit",
        "contract_title": "Contrat méthodologique",
        "contract_items": [
            "Aucun pourcentage affiché sous n=30 ; les sous-groupes sont rapportés en effectifs bruts. Les intervalles de confiance sont des Wilson à 95%.",
            "Un thème est « étayé » quand signal quantitatif et entretiens concordent par des voies indépendantes (n≥30 + effet significatif) ; « solide » exige n≥100 et un effet équivalent p<0,01 ; en deçà, il est « indicatif ».",
            "Chaque citation d'ancrage est vérifiée après génération comme extrait verbatim d'un vrai transcript d'entretien ; les citations invérifiables sont retirées automatiquement.",
            "Analyse générée par IA (Claude) à partir des agrégats du sondage et des transcripts d'entretien, relue par l'équipe de recherche avant diffusion.",
        ],
        "evidence_index": "Index des preuves",
        "idx_surveys": "Questionnaires",
        "idx_interviews": "Entretiens",
        "col_instrument": "Instrument", "col_status": "Statut",
        "col_questions": "Questions", "col_completed": "Complétées",
        "col_id": "ID", "col_name": "Participant", "col_profession": "Profession",
        "col_country": "Pays", "col_turns": "Tours",
        "anonymous": "Participant",
        "footer": "Généré avec QualiPulse — signal quantitatif et preuves d'entretien combinés, avec traçabilité complète des citations.",
        "print_btn": "Imprimer / Enregistrer en PDF",
    },
}

# Serif-led, evergreen document design — deliberately closer to a consulting
# memo than to the app UI. Self-contained (no webfonts), print-exact colors.
_STUDY_CSS = """
:root {
  --paper: #fcfcfa; --ink: #17201b; --ink-2: #4c5852; --ink-3: #7a847e;
  --rule: #dfe5e0; --rule-strong: #17201b;
  --accent: #1d5c3f; --accent-tint: #eef4ef;
  --copper: #a2541f; --amber: #8a5a17; --amber-tint: #f6efdf;
  --gap-bg: #edefed;
  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, "Charter", Georgia, serif;
  --sans: "Avenir Next", "Segoe UI", -apple-system, "Helvetica Neue", sans-serif;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: var(--sans); color: var(--ink); background: var(--paper);
  font-size: 15px; line-height: 1.6; }
.sheet { max-width: 780px; margin: 0 auto; padding: 56px 40px 64px; }
@media (max-width: 720px) { .sheet { padding: 32px 20px; } }
.num, .tabular { font-variant-numeric: tabular-nums; }

.eyebrow { font-size: 11px; font-weight: 600; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--accent); }
.cover { border-bottom: 2px solid var(--rule-strong); padding-bottom: 24px; }
.cover__brand { display: flex; align-items: baseline; gap: 12px; }
.cover__logo { font-weight: 700; font-size: 1rem; color: var(--accent); letter-spacing: -0.01em; }
.cover__title { font-family: var(--serif); font-size: 2.1rem; font-weight: 600;
  line-height: 1.22; letter-spacing: -0.01em; margin: 12px 0 14px; text-wrap: balance; }
.cover__meta { display: flex; flex-wrap: wrap; gap: 6px 24px; font-size: 12.5px; color: var(--ink-2); }
.cover__meta strong { color: var(--ink); font-weight: 600; }

section { margin-top: 46px; }
.sec-head { display: flex; align-items: baseline; gap: 14px;
  border-bottom: 1px solid var(--rule); padding-bottom: 8px; margin-bottom: 20px; }
.sec-num { font-family: var(--serif); font-size: 0.95rem; color: var(--ink-3); }
.sec-title { font-size: 12px; font-weight: 700; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--ink); }

.verdict { font-family: var(--serif); font-size: 1.4rem; line-height: 1.45;
  font-weight: 500; margin-bottom: 22px; max-width: 60ch; text-wrap: balance; }
.findings { display: flex; flex-direction: column; gap: 14px; }
.finding { display: grid; grid-template-columns: 28px 1fr; gap: 12px; align-items: start; }
.finding__num { font-family: var(--serif); font-size: 1.15rem; color: var(--accent); }
.finding p { margin: 2px 0 0; }

.chip { display: inline-block; font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; padding: 2px 8px; border-radius: 3px; white-space: nowrap;
  vertical-align: 1px; }
.chip--strong, .chip--supported { background: var(--accent-tint); color: var(--accent); }
.chip--directional { background: var(--amber-tint); color: var(--amber); }
.chip--gap { background: var(--gap-bg); color: var(--ink-2); }

.stat-band { display: grid; grid-template-columns: repeat(4, 1fr); gap: 22px; margin-bottom: 30px; }
@media (max-width: 640px) { .stat-band { grid-template-columns: repeat(2, 1fr); } }
.stat__value { font-family: var(--serif); font-size: 1.9rem; font-weight: 600;
  line-height: 1.1; font-variant-numeric: tabular-nums; }
.stat__label { font-size: 11.5px; color: var(--ink-2); margin-top: 4px; line-height: 1.4; }

figure { margin: 0 0 26px; }
.chart-title { font-size: 13px; font-weight: 600; margin-bottom: 2px; max-width: 70ch; }
.chart-meta { font-size: 11.5px; color: var(--ink-3); margin-bottom: 10px; }
.chart-wrap { overflow-x: auto; }
figcaption { font-size: 12px; color: var(--ink-2); margin-top: 6px; max-width: 70ch; }
.survey-block > h3 { font-size: 12px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--ink-2); margin: 26px 0 16px; }

.theme-title { font-family: var(--serif); font-size: 1.35rem; font-weight: 600;
  line-height: 1.3; margin-bottom: 6px; text-wrap: balance; }
.theme-title .chip { margin-left: 10px; }
.confidence-why { font-size: 12.5px; color: var(--ink-2); margin-bottom: 18px; max-width: 74ch; }
.evidence-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 26px; margin: 6px 0 16px; }
@media (max-width: 640px) { .evidence-grid { grid-template-columns: 1fr; } }
.evidence-col h4 { font-size: 11px; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--ink-2); margin-bottom: 10px; }
.signal-summary { font-family: var(--serif); font-size: 1.05rem; line-height: 1.45; margin-bottom: 6px; }
.signal-meta { font-size: 12px; color: var(--ink-3); }
blockquote { margin: 0 0 10px; padding-left: 14px; border-left: 2px solid var(--rule); }
blockquote p { font-family: var(--serif); font-size: 1rem; font-style: italic;
  line-height: 1.5; margin-bottom: 4px; }
blockquote footer { font-size: 12px; color: var(--ink-2); }
.validation-row { border-top: 1px solid var(--rule); padding-top: 12px; margin-top: 4px;
  font-size: 13px; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.validation-row .lbl { font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--ink-2); }
.validation-bar { display: inline-block; width: 120px; height: 8px; background: var(--gap-bg);
  border-radius: 4px; overflow: hidden; vertical-align: middle; }
.validation-bar i { display: block; height: 100%; background: var(--accent); }
.so-what { background: var(--accent-tint); border-left: 3px solid var(--accent);
  padding: 14px 18px; margin-top: 14px; max-width: 660px; }
.so-what .lbl { font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--accent); display: block; margin-bottom: 4px; }
.so-what p { font-size: 13.5px; margin: 0; }
.so-what .rationale-line { color: var(--ink-2); font-size: 12.5px; margin-top: 4px; }

.method-note { font-size: 13.5px; max-width: 74ch; margin-bottom: 8px; }
.contract { background: #f4f6f4; padding: 16px 20px; font-size: 13px; margin-top: 18px; max-width: 680px; }
.contract h4 { font-size: 11px; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--ink-2); margin-bottom: 8px; }
.contract ul { margin: 0; padding-left: 18px; }
.contract li { margin-bottom: 5px; }
.idx { margin-top: 24px; }
.idx h4 { font-size: 11px; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--ink-2); margin-bottom: 10px; }
.idx table { border-collapse: collapse; width: 100%; font-size: 12.5px; margin-bottom: 18px; }
.idx th { text-align: left; font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--ink-2); border-bottom: 1.5px solid var(--rule-strong);
  padding: 0 14px 6px 0; }
.idx td { border-bottom: 1px solid var(--rule); padding: 8px 14px 8px 0; vertical-align: top; }

.doc-footer { margin-top: 52px; border-top: 1px solid var(--rule); padding-top: 14px;
  font-size: 12px; color: var(--ink-3); display: flex; justify-content: space-between;
  flex-wrap: wrap; gap: 8px; }
.doc-footer strong { color: var(--accent); }
.toolbar { position: fixed; top: 18px; right: 18px; z-index: 10; }
.toolbar button { font: inherit; font-size: 0.82rem; font-weight: 600; color: #fff;
  background: var(--accent); border: 0; border-radius: 999px; padding: 10px 18px;
  cursor: pointer; box-shadow: 0 4px 16px rgba(23,32,27,0.18); }
.toolbar button:hover { background: #16452f; }
.avoid-break { break-inside: avoid; page-break-inside: avoid; }
svg text { font-family: var(--sans); }
@media print {
  body { background: #fff; font-size: 12.5px; }
  .sheet { max-width: none; padding: 0; }
  .toolbar { display: none; }
  section { margin-top: 30px; }
  @page { size: A4; margin: 16mm 14mm; }
}
"""


def _truncate_label(text: str, limit: int = 36) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _svg_choice_bars(choices: list[dict], lang: str) -> str:
    """Horizontal bar chart for a multiple-choice breakdown.

    Counts are always printed on the bar; percentages (+ Wilson CI) only
    when the analytics layer released them (n>=30) — the renderer never
    computes a percentage itself.
    """
    rows = [c for c in choices if c.get("label") is not None]
    if not rows:
        return ""
    max_count = max((c.get("count") or 0) for c in rows) or 1
    row_h, label_w, bar_max = 28, 250, 260
    height = len(rows) * row_h + 6
    parts = [
        f'<svg viewBox="0 0 680 {height}" width="100%" role="img">',
    ]
    for i, c in enumerate(rows):
        y = i * row_h
        count = c.get("count") or 0
        w = max(2, round(bar_max * count / max_count)) if count else 0
        opacity = max(0.35, 1 - i * 0.16)
        label = _esc(_truncate_label(str(c.get("label"))))
        pct = c.get("percentage")
        if pct is not None:
            value = f"{count} · {round(pct)}%"
            ci_low, ci_high = c.get("ci_low"), c.get("ci_high")
            if ci_low is not None and ci_high is not None:
                value += f" [{round(ci_low)}–{round(ci_high)}]"
        else:
            value = str(count)
        parts.append(f'<text x="0" y="{y + 18}" font-size="12" fill="#17201b">{label}</text>')
        if count:
            parts.append(
                f'<rect x="{label_w}" y="{y + 8}" width="{w}" height="13" '
                f'fill="#1d5c3f" opacity="{opacity:.2f}"/>'
            )
        parts.append(
            f'<text x="{label_w + w + 8}" y="{y + 19}" font-size="11.5" '
            f'font-weight="600" fill="#4c5852">{_esc(value)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _svg_histogram(histogram: list[dict], mean: float | None) -> str:
    """Column chart for a likert / NPS bucket histogram (counts always shown)."""
    buckets = [(h.get("bucket"), h.get("count") or 0) for h in histogram]
    if not buckets:
        return ""
    max_count = max(c for _, c in buckets) or 1
    n_buckets = len(buckets)
    plot_w, base_y, plot_h, left = 620, 130, 105, 30
    slot = plot_w / n_buckets
    bar_w = min(34, slot * 0.6)
    parts = [
        f'<svg viewBox="0 0 680 165" width="100%" role="img">',
        f'<line x1="{left}" y1="{base_y}" x2="{left + plot_w}" y2="{base_y}" stroke="#dfe5e0"/>',
    ]
    for i, (bucket, count) in enumerate(buckets):
        cx = left + slot * i + slot / 2
        h = round(plot_h * count / max_count) if count else 0
        if count:
            parts.append(
                f'<rect x="{cx - bar_w / 2:.1f}" y="{base_y - h}" width="{bar_w:.1f}" '
                f'height="{h}" fill="#1d5c3f"/>'
            )
            parts.append(
                f'<text x="{cx:.1f}" y="{base_y - h - 5}" font-size="10.5" '
                f'text-anchor="middle" fill="#4c5852">{count}</text>'
            )
        parts.append(
            f'<text x="{cx:.1f}" y="{base_y + 16}" font-size="11" '
            f'text-anchor="middle" fill="#7a847e">{_esc(bucket)}</text>'
        )
    if mean is not None and n_buckets > 1:
        first = buckets[0][0]
        last = buckets[-1][0]
        try:
            span = float(last) - float(first)
            if span > 0:
                mx = left + slot / 2 + (float(mean) - float(first)) / span * (plot_w - slot)
                parts.append(
                    f'<line x1="{mx:.1f}" y1="18" x2="{mx:.1f}" y2="{base_y}" '
                    f'stroke="#a2541f" stroke-width="1" stroke-dasharray="3 3"/>'
                )
                parts.append(
                    f'<text x="{mx:.1f}" y="12" font-size="10.5" text-anchor="middle" '
                    f'fill="#a2541f">{float(mean):.1f}</text>'
                )
        except (TypeError, ValueError):
            pass
    parts.append("</svg>")
    return "".join(parts)


def _study_confidence_chip(confidence: str, L: dict) -> str:
    c = (confidence or "").lower()
    label = L.get(f"conf_{c}", _esc(confidence))
    return f'<span class="chip chip--{_esc(c)}">{label}</span>'


def _confidence_why(theme: dict, L: dict) -> str:
    """Deterministic one-line rationale for a theme's confidence pill.

    Built from the same fields the calibration thresholds run on (n,
    segment, interview corroboration) — no AI involved, so the rationale
    can never drift from the data.
    """
    parts = []
    signal = theme.get("survey_signal") or {}
    evidence = theme.get("interview_evidence") or {}
    if signal.get("n"):
        parts.append(L["why_survey_n"].format(n=signal["n"]))
    if signal.get("segment_label"):
        parts.append(L["why_segment"].format(s=signal["segment_label"]))
    if signal.get("segment_over_index"):
        parts.append(L["why_lift"].format(lift=round(signal["segment_over_index"], 1)))
    if evidence.get("x_of_y"):
        parts.append(L["why_interviews"].format(x=evidence["x_of_y"]))
    elif signal:
        parts.append(L["why_survey_only"])
    joined = _esc(", ".join(parts)) if parts else "—"
    template = L.get(f"why_{(theme.get('confidence') or '').lower()}")
    if not template:
        return ""
    return f'<p class="confidence-why">{template.format(parts=joined)}</p>'


def _theme_validation_row(snapshot, L: dict) -> str:
    """Respondent-validation line for one theme (Wilson-CI or raw counts)."""
    if snapshot is None or snapshot.n_answered == 0:
        return (
            f'<div class="validation-row"><span class="lbl">{L["validation_label"]}</span>'
            f'<span class="chip chip--gap">{L["validation_awaiting"]}</span></div>'
        )
    if snapshot.agreement_pct is not None:
        pct = round(snapshot.agreement_pct)
        text = L["validation_agree_pct"].format(
            pct=pct,
            lo=round(snapshot.ci_low) if snapshot.ci_low is not None else "—",
            hi=round(snapshot.ci_high) if snapshot.ci_high is not None else "—",
            n=snapshot.n_answered,
        )
        bar = f'<span class="validation-bar"><i style="width:{pct}%"></i></span>'
    else:
        agree = (snapshot.distribution or {}).get(4, 0) + (snapshot.distribution or {}).get(5, 0)
        text = L["validation_agree_counts"].format(agree=agree, n=snapshot.n_answered)
        width = round(100 * agree / snapshot.n_answered) if snapshot.n_answered else 0
        bar = f'<span class="validation-bar"><i style="width:{width}%"></i></span>'
    return (
        f'<div class="validation-row"><span class="lbl">{L["validation_label"]}</span>'
        f'{bar}<span class="num">{_esc(text)}</span></div>'
    )


def render_study_report_html(
    study,
    analysis,
    dashboards: list,
    validation,
    participants: list,
    turn_counts: dict,
    company_name: str = "",
) -> str:
    """Standalone print-ready HTML for one StudyAnalysis (Quantified Themes).

    Everything rendered is either straight from the stored report JSON or
    deterministically computed from the same aggregates the generation
    pipeline used (``build_dashboard`` / ``compute_validation_summary``) —
    the renderer never invents numbers and never shows a percentage the
    stats layer suppressed.

    ``dashboards``   — SurveyDashboardPayload list (validation surveys excluded).
    ``validation``   — ValidationSummary | None for this analysis.
    ``participants`` — completed Participants across the study's projects.
    ``turn_counts``  — participant_id → number of turns (evidence index).
    """
    company_lang = getattr(getattr(study, "company", None), "preferred_language", None)
    lang = "fr" if (company_lang or "en").lower().startswith("fr") else "en"
    L = _STUDY_STRINGS[lang]

    report = json.loads(analysis.report) if analysis.report else {}
    themes = report.get("themes", []) or []

    n_responses = report.get("generated_with_response_count") or sum(
        d.n_completed for d in dashboards
    )
    n_interviews = report.get("generated_with_interview_count") or len(participants)
    generated = _fmt_date(analysis.generated_at, lang)

    # ── header ────────────────────────────────────────────────────────────
    header = f"""
    <header class="cover">
      <div class="cover__brand">
        <span class="cover__logo">QualiPulse</span>
        <span class="eyebrow">{L["doc_type"]}</span>
      </div>
      <h1 class="cover__title">{_esc(study.name)}</h1>
      <div class="cover__meta num">
        <span><strong>{n_responses}</strong> {L["responses"]}</span>
        <span><strong>{n_interviews}</strong> {L["interviews"]}</span>
        <span>{L["version"].format(v=analysis.version)}</span>
        <span>{L["generated"]} {generated}</span>
      </div>
    </header>
    """

    # ── 1. essentials: verdict + numbered findings ────────────────────────
    findings = "".join(
        f"""<div class="finding">
          <span class="finding__num num">{i + 1}.</span>
          <p><strong>{_esc(t.get("title", ""))}</strong> {_study_confidence_chip(t.get("confidence", ""), L)}</p>
        </div>"""
        for i, t in enumerate(themes)
    )
    essentials = f"""
    <section class="avoid-break">
      <div class="sec-head"><span class="sec-num num">1</span><span class="sec-title">{L["sec_essentials"]}</span></div>
      <p class="verdict">{_esc(report.get("executive_summary", ""))}</p>
      <div class="findings">{findings}</div>
    </section>
    """

    # ── 2. evidence at a glance: stat band + per-question charts ─────────
    validated_count = 0
    if validation is not None:
        validated_count = sum(
            1 for s in validation.per_theme.values() if s.n_answered > 0
        )
    if validation is not None and validated_count:
        stat4 = f'<div class="stat"><div class="stat__value num">{validated_count}/{len(themes)}</div><div class="stat__label">{L["stat_validated"]}</div></div>'
    else:
        stat4 = f'<div class="stat"><div class="stat__value num">{len(dashboards)}</div><div class="stat__label">{L["stat_surveys"]}</div></div>'
    stat_band = f"""
    <div class="stat-band">
      <div class="stat"><div class="stat__value num">{n_responses}</div><div class="stat__label">{L["stat_responses"]}</div></div>
      <div class="stat"><div class="stat__value num">{n_interviews}</div><div class="stat__label">{L["stat_interviews"]}</div></div>
      <div class="stat"><div class="stat__value num">{len(themes)}</div><div class="stat__label">{L["stat_themes"]}</div></div>
      {stat4}
    </div>
    """

    chart_blocks = []
    for dash in dashboards:
        figures = []
        for q in dash.questions:
            if q.n_answered == 0:
                continue
            meta_bits = [L["chart_n"].format(n=q.n_answered)]
            body = ""
            caption = ""
            if q.type in ("likert", "nps"):
                hist = (q.breakdown or {}).get("histogram") or []
                if not any((h.get("count") or 0) for h in hist):
                    continue
                if q.mean is not None:
                    meta_bits.append(L["chart_mean"].format(m=f"{q.mean:.1f}"))
                body = _svg_histogram(hist, q.mean)
                nps_score = (q.breakdown or {}).get("nps_score")
                if nps_score is not None:
                    caption = L["chart_nps"].format(
                        score=nps_score,
                        p=(q.breakdown or {}).get("promoters", 0),
                        pa=(q.breakdown or {}).get("passives", 0),
                        d=(q.breakdown or {}).get("detractors", 0),
                    )
            elif q.type in ("mc_single", "mc_multi"):
                choices = (q.breakdown or {}).get("choices") or []
                if not choices:
                    continue
                body = _svg_choice_bars(choices, lang)
                if all(c.get("percentage") is None for c in choices):
                    caption = L["chart_no_pct"]
            elif q.type in ("open_text", "short_text"):
                total = (q.breakdown or {}).get("total_texts", q.n_answered)
                figures.append(
                    f'<figure class="avoid-break"><div class="chart-title">{_esc(q.prompt)}</div>'
                    f'<figcaption>{L["chart_open_text"].format(n=total)}</figcaption></figure>'
                )
                continue
            if not body:
                continue
            caption_html = f"<figcaption>{_esc(caption)}</figcaption>" if caption else ""
            figures.append(
                f'<figure class="avoid-break"><div class="chart-title">{_esc(q.prompt)}</div>'
                f'<div class="chart-meta num">{_esc(" · ".join(meta_bits))}</div>'
                f'<div class="chart-wrap">{body}</div>{caption_html}</figure>'
            )
        if figures:
            chart_blocks.append(
                f'<div class="survey-block"><h3>{_esc(dash.name)}</h3>{"".join(figures)}</div>'
            )
    evidence = f"""
    <section>
      <div class="sec-head"><span class="sec-num num">2</span><span class="sec-title">{L["sec_evidence"]}</span></div>
      {stat_band}
      {"".join(chart_blocks)}
    </section>
    """

    # ── 3..N theme sections ───────────────────────────────────────────────
    theme_sections = []
    for i, theme in enumerate(themes):
        signal = theme.get("survey_signal") or {}
        ev = theme.get("interview_evidence") or {}
        reco = theme.get("recommendation") or {}

        cols = []
        if signal:
            meta = [L["chart_n"].format(n=signal.get("n", "—"))]
            if signal.get("segment_label"):
                meta.append(_esc(signal["segment_label"]))
            if signal.get("segment_over_index"):
                meta.append(L["why_lift"].format(lift=round(signal["segment_over_index"], 1)))
            cols.append(
                f'<div class="evidence-col"><h4>{L["survey_signal"]}</h4>'
                f'<p class="signal-summary">{_esc(signal.get("summary", ""))}</p>'
                f'<p class="signal-meta num">{" · ".join(meta)}</p></div>'
            )
        if ev and ev.get("anchor_quote"):
            segments = ", ".join(ev.get("segments_mentioned") or [])
            seg_line = (
                f'<footer>{_esc(L["segments_mentioned"].format(s=segments))}</footer>'
                if segments
                else ""
            )
            cols.append(
                f'<div class="evidence-col"><h4>{_esc(L["interview_evidence"].format(x=ev.get("x_of_y", "")))}</h4>'
                f'<blockquote><p>«&nbsp;{_esc(ev["anchor_quote"])}&nbsp;»</p>{seg_line}</blockquote></div>'
            )

        validation_html = ""
        if validation is not None:
            validation_html = _theme_validation_row(validation.per_theme.get(i), L)

        reco_html = ""
        if reco.get("action"):
            kind_label = L.get(f"reco_{(reco.get('kind') or '').lower()}", "")
            rationale = (
                f'<p class="rationale-line">{_esc(reco.get("rationale") or "")}</p>'
                if reco.get("rationale")
                else ""
            )
            reco_html = (
                f'<div class="so-what"><span class="lbl">{kind_label}</span>'
                f'<p><strong>{_esc(reco["action"])}</strong></p>{rationale}</div>'
            )

        theme_sections.append(f"""
        <section class="avoid-break">
          <div class="sec-head"><span class="sec-num num">{i + 3}</span><span class="sec-title">{L["sec_theme"].format(i=i + 1)}</span></div>
          <h2 class="theme-title">{_esc(theme.get("title", ""))}{_study_confidence_chip(theme.get("confidence", ""), L)}</h2>
          {_confidence_why(theme, L)}
          <div class="evidence-grid">{"".join(cols)}</div>
          {validation_html}
          {reco_html}
        </section>
        """)

    # ── methodology + evidence index ──────────────────────────────────────
    contract_items = "".join(f"<li>{item}</li>" for item in L["contract_items"])
    survey_rows = "".join(
        f"<tr><td>{_esc(d.name)}</td><td>{_esc(d.status)}</td>"
        f'<td class="num">{len(d.questions)}</td><td class="num">{d.n_completed}</td></tr>'
        for d in dashboards
    )
    surveys_table = (
        f'<h4>{L["idx_surveys"]}</h4><table><thead><tr>'
        f'<th>{L["col_instrument"]}</th><th>{L["col_status"]}</th>'
        f'<th>{L["col_questions"]}</th><th>{L["col_completed"]}</th>'
        f"</tr></thead><tbody>{survey_rows}</tbody></table>"
        if survey_rows
        else ""
    )
    participant_rows = "".join(
        f'<tr><td class="num">E-{i + 1:02d}</td>'
        f'<td>{_esc(p.display_name or L["anonymous"])}</td>'
        f"<td>{_esc(p.profession or '—')}</td><td>{_esc(p.country or '—')}</td>"
        f'<td class="num">{turn_counts.get(p.id, "—")}</td></tr>'
        for i, p in enumerate(participants)
    )
    interviews_table = (
        f'<h4>{L["idx_interviews"]}</h4><table><thead><tr>'
        f'<th>{L["col_id"]}</th><th>{L["col_name"]}</th><th>{L["col_profession"]}</th>'
        f'<th>{L["col_country"]}</th><th>{L["col_turns"]}</th>'
        f"</tr></thead><tbody>{participant_rows}</tbody></table>"
        if participant_rows
        else ""
    )
    methodology_note = report.get("methodology_note") or ""
    methodology = f"""
    <section>
      <div class="sec-head"><span class="sec-num num">{len(themes) + 3}</span><span class="sec-title">{L["sec_methodology"]}</span></div>
      <p class="method-note">{_esc(methodology_note)}</p>
      <div class="contract avoid-break"><h4>{L["contract_title"]}</h4><ul>{contract_items}</ul></div>
      <div class="idx">{surveys_table}{interviews_table}</div>
    </section>
    """

    title = f"{study.name} — {L['doc_type']}"
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{_esc(title)}</title>
<style>{_STUDY_CSS}</style>
</head>
<body>
<div class="toolbar"><button onclick="window.print()">{L["print_btn"]}</button></div>
<div class="sheet">
{header}
{essentials}
{evidence}
{"".join(theme_sections)}
{methodology}
<footer class="doc-footer">
  <span><strong>QualiPulse</strong> · {_esc(company_name)}</span>
  <span>{L["footer"]}</span>
</footer>
</div>
</body>
</html>"""
