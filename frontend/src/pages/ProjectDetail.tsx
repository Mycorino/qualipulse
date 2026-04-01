import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  getProject,
  getLinks,
  getParticipants,
  createLink,
  getTranscript,
  exportCSV,
  deleteProject,
  getAnalysis,
  triggerAnalysis,
  ProjectResponse,
  InterviewLink,
  ParticipantResponse,
  TranscriptTurn,
  AnalysisResponse,
} from "../api/projects";

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [links, setLinks] = useState<InterviewLink[]>([]);
  const [participants, setParticipants] = useState<ParticipantResponse[]>([]);
  const [transcript, setTranscript] = useState<TranscriptTurn[] | null>(null);
  const [selectedParticipant, setSelectedParticipant] =
    useState<ParticipantResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [linkCopied, setLinkCopied] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [analysisPolling, setAnalysisPolling] = useState(false);

  useEffect(() => {
    if (!id) return;
    loadAll();
  }, [id]);

  async function loadAll() {
    setLoading(true);
    try {
      const [proj, lnks, parts, ana] = await Promise.all([
        getProject(id!),
        getLinks(id!),
        getParticipants(id!),
        getAnalysis(id!),
      ]);
      setProject(proj);
      setLinks(lnks);
      setParticipants(parts);
      setAnalysis(ana);
      if (ana.status === "generating") startPolling();
    } catch {
      // handled by interceptor
    } finally {
      setLoading(false);
    }
  }

  function startPolling() {
    if (analysisPolling) return;
    setAnalysisPolling(true);
    const iv = setInterval(async () => {
      const ana = await getAnalysis(id!);
      setAnalysis(ana);
      if (ana.status !== "generating") {
        clearInterval(iv);
        setAnalysisPolling(false);
      }
    }, 3000);
  }

  async function handleTriggerAnalysis() {
    await triggerAnalysis(id!);
    setAnalysis((prev) => prev ? { ...prev, status: "generating" } : null);
    startPolling();
  }

  async function handleGenerateLink() {
    try {
      const link = await createLink(id!);
      setLinks((prev) => [...prev, link]);
    } catch {
      alert("Failed to generate link");
    }
  }

  function interviewUrl(token: string) {
    return `${window.location.origin}/i/${token}`;
  }

  async function copyLink(token: string) {
    await navigator.clipboard.writeText(interviewUrl(token));
    setLinkCopied(true);
    setTimeout(() => setLinkCopied(false), 2000);
  }

  async function handleViewTranscript(p: ParticipantResponse) {
    setSelectedParticipant(p);
    try {
      const t = await getTranscript(id!, p.id);
      setTranscript(t);
    } catch {
      setTranscript([]);
    }
  }

  async function handleExportCSV() {
    try {
      const blob = await exportCSV(id!);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${project?.name || "export"}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert("Failed to export CSV");
    }
  }

  async function handleDelete() {
    if (!confirm("Are you sure you want to delete this project?")) return;
    try {
      await deleteProject(id!);
      navigate("/dashboard");
    } catch {
      alert("Failed to delete project");
    }
  }

  if (loading) {
    return (
      <div className="page-center">
        <p className="muted-text">Loading project...</p>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="page-center">
        <p>Project not found.</p>
      </div>
    );
  }

  // Group questions by section
  const sections = project.questions.reduce(
    (acc, q) => {
      if (!acc[q.section_title]) acc[q.section_title] = [];
      acc[q.section_title].push(q);
      return acc;
    },
    {} as Record<string, typeof project.questions>
  );

  return (
    <div className="detail-layout">
      <header className="detail-header">
        <button className="btn btn-ghost" onClick={() => navigate("/dashboard")}>
          &larr; Back
        </button>
        <div className="detail-header-actions">
          <button className="btn btn-ghost" onClick={handleExportCSV}>
            Export CSV
          </button>
          <button className="btn btn-ghost" onClick={() => navigate(`/projects/${id}/edit`)}>
            Edit
          </button>
          <button
            className="btn btn-ghost btn-danger-text"
            onClick={handleDelete}
          >
            Delete
          </button>
        </div>
      </header>

      <main className="detail-main">
        {/* Project Info */}
        <section className="detail-section">
          <h1>{project.name}</h1>
          <div className="detail-meta">
            <span className="badge">{project.language.toUpperCase()}</span>
            <span>{project.interview_duration_minutes} min</span>
            <span>{project.questions.length} questions</span>
          </div>
        </section>

        {/* Research Objective */}
        {project.research_objective && (
          <section className="detail-section">
            <h2>Research Objective</h2>
            <p>{project.research_objective}</p>
          </section>
        )}

        {/* Interview Links */}
        <section className="detail-section">
          <div className="section-header-row">
            <h2>Interview Links</h2>
            {links.length === 0 && (
              <button className="btn btn-primary btn-sm" onClick={handleGenerateLink}>
                Generate Link
              </button>
            )}
          </div>
          {links.length === 0 ? (
            <p className="muted-text">
              No links yet. Generate one to share with participants.
            </p>
          ) : (
            <div className="links-list">
              {links.map((l) => (
                <div key={l.id} className="link-row">
                  <code className="link-url">{interviewUrl(l.token)}</code>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => copyLink(l.token)}
                  >
                    {linkCopied ? "Copied!" : "Copy"}
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* AI Analysis */}
        {analysis && (
          <section className="detail-section">
            <div className="section-header-row">
              <h2>AI Analysis</h2>
              {analysis.completed_count > 0 && (
                <button
                  className="btn btn-ai btn-sm"
                  onClick={handleTriggerAnalysis}
                  disabled={analysis.status === "generating"}
                >
                  {analysis.status === "generating"
                    ? "Analysing..."
                    : analysis.status === "none"
                    ? "✦ Generate Analysis"
                    : "✦ Regenerate"}
                </button>
              )}
            </div>

            {analysis.status === "none" && analysis.completed_count === 0 && (
              <p className="muted-text">Complete at least one interview to generate an analysis.</p>
            )}

            {analysis.status === "none" && analysis.completed_count > 0 && (
              <p className="muted-text">{analysis.completed_count} completed interview{analysis.completed_count > 1 ? "s" : ""} ready to analyse.</p>
            )}

            {analysis.status === "generating" && (
              <div className="analysis-generating">
                <span className="spinner-sm" />
                <span>Claude is reading {analysis.participant_count} interview{analysis.participant_count !== 1 ? "s" : ""}...</span>
              </div>
            )}

            {analysis.status === "failed" && (
              <p className="muted-text" style={{ color: "var(--danger)" }}>Analysis failed: {analysis.error}</p>
            )}

            {analysis.status === "ready" && analysis.report && (() => {
              const r = analysis.report;
              const isStale = analysis.completed_count > analysis.participant_count;
              return (
                <div className="analysis-report">
                  {isStale && (
                    <div className="analysis-stale-banner">
                      {analysis.completed_count - analysis.participant_count} new response{analysis.completed_count - analysis.participant_count > 1 ? "s" : ""} since last analysis — regenerate to include them.
                    </div>
                  )}

                  <div className="analysis-summary">{r.summary}</div>

                  <div className="analysis-meta">
                    <span className="badge">Based on {r.participant_count} interviews</span>
                    <span className="badge">Confidence: {r.confidence}</span>
                    {analysis.generated_at && (
                      <span className="muted-text" style={{ fontSize: "0.8rem" }}>
                        Generated {new Date(analysis.generated_at).toLocaleString()}
                      </span>
                    )}
                  </div>

                  {r.themes.length > 0 && (
                    <div className="analysis-block">
                      <h3>Key Themes</h3>
                      {r.themes.map((t, i) => (
                        <div key={i} className="analysis-theme">
                          <div className="analysis-theme-header">
                            <strong>{t.title}</strong>
                            <span className="badge">{t.frequency}</span>
                          </div>
                          <p>{t.summary}</p>
                          {t.quotes.length > 0 && (
                            <div className="analysis-quotes">
                              {t.quotes.map((q, j) => (
                                <blockquote key={j} className="analysis-quote">"{q}"</blockquote>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {r.jobs_to_be_done.length > 0 && (
                    <div className="analysis-block">
                      <h3>Jobs to be Done</h3>
                      {r.jobs_to_be_done.map((j, i) => (
                        <div key={i} className="analysis-jtbd">
                          <div className="analysis-jtbd-job">"{j.job}"</div>
                          <p className="analysis-jtbd-insight">{j.insight}</p>
                          <span className="badge">{j.frequency}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {r.tensions.length > 0 && (
                    <div className="analysis-block">
                      <h3>Tensions & Contradictions</h3>
                      {r.tensions.map((t, i) => (
                        <div key={i} className="analysis-tension">
                          <strong>{t.tension}</strong>
                          <p>{t.detail}</p>
                        </div>
                      ))}
                    </div>
                  )}

                  {r.recommendations.length > 0 && (
                    <div className="analysis-block">
                      <h3>Recommendations</h3>
                      <ol className="analysis-recommendations">
                        {r.recommendations.map((rec, i) => (
                          <li key={i}>{rec}</li>
                        ))}
                      </ol>
                    </div>
                  )}
                </div>
              );
            })()}
          </section>
        )}

        {/* Interview Guide */}
        <section className="detail-section">
          <h2>Interview Guide</h2>
          {Object.entries(sections).map(([title, qs]) => (
            <div key={title} className="guide-section">
              <h3 className="guide-section-title">{title}</h3>
              <ol className="guide-questions">
                {qs
                  .sort((a, b) => a.question_index - b.question_index)
                  .map((q) => (
                    <li key={q.id} className="guide-question">
                      {q.main_question}
                    </li>
                  ))}
              </ol>
            </div>
          ))}
          {project.questions.length === 0 && (
            <p className="muted-text">No questions defined.</p>
          )}
        </section>

        {/* Participants */}
        <section className="detail-section">
          <h2>Participants ({participants.length})</h2>
          {participants.length === 0 ? (
            <p className="muted-text">No participants yet.</p>
          ) : (
            <div className="participants-list">
              {participants.map((p) => (
                <div
                  key={p.id}
                  className={`participant-row ${
                    selectedParticipant?.id === p.id ? "active" : ""
                  }`}
                  onClick={() => handleViewTranscript(p)}
                >
                  <div>
                    <span className="participant-name">
                      {p.display_name || "Anonymous"}
                    </span>
                    <span
                      className={`status-badge ${
                        p.status === "completed" ? "status-done" : "status-progress"
                      }`}
                    >
                      {p.status === "completed" ? "Completed" : "In Progress"}
                    </span>
                  </div>
                  <span className="participant-date">
                    {new Date(p.started_at).toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Transcript */}
        {transcript !== null && selectedParticipant && (
          <section className="detail-section transcript-section">
            <div className="section-header-row">
              <h2>
                Transcript &mdash;{" "}
                {selectedParticipant.display_name || "Anonymous"}
              </h2>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setTranscript(null);
                  setSelectedParticipant(null);
                }}
              >
                Close
              </button>
            </div>
            {transcript.length === 0 ? (
              <p className="muted-text">No transcript available.</p>
            ) : (
              <div className="transcript-list">
                {transcript.map((t) => (
                  <div key={t.turn_index} className="transcript-turn">
                    <div className="transcript-q">
                      <strong>Q:</strong> {t.question_text}
                    </div>
                    {t.response_transcript && (
                      <div className="transcript-a">
                        <strong>A:</strong> {t.response_transcript}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
