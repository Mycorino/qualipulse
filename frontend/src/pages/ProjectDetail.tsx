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
  ProjectResponse,
  InterviewLink,
  ParticipantResponse,
  TranscriptTurn,
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

  useEffect(() => {
    if (!id) return;
    loadAll();
  }, [id]);

  async function loadAll() {
    setLoading(true);
    try {
      const [proj, lnks, parts] = await Promise.all([
        getProject(id!),
        getLinks(id!),
        getParticipants(id!),
      ]);
      setProject(proj);
      setLinks(lnks);
      setParticipants(parts);
    } catch {
      // handled by interceptor
    } finally {
      setLoading(false);
    }
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

        {/* Interview Links */}
        <section className="detail-section">
          <div className="section-header-row">
            <h2>Interview Links</h2>
            <button className="btn btn-primary btn-sm" onClick={handleGenerateLink}>
              Generate Link
            </button>
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
                  <div key={t.id} className="transcript-turn">
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
