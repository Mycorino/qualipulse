import { useState, useEffect, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import {
  listProjects,
  createProject,
  importProjectCSV,
  ProjectListItem,
  QuestionCreate,
} from "../api/projects";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "es", label: "Spanish" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
  { code: "it", label: "Italian" },
  { code: "pt", label: "Portuguese" },
  { code: "nl", label: "Dutch" },
  { code: "ja", label: "Japanese" },
  { code: "ko", label: "Korean" },
  { code: "zh", label: "Chinese" },
];

export default function Dashboard() {
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { logout } = useAuth();

  useEffect(() => {
    loadProjects();
  }, []);

  async function loadProjects() {
    try {
      const data = await listProjects();
      setProjects(data);
    } catch {
      // handled by interceptor
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="dashboard-layout">
      <header className="dashboard-header">
        <h1 className="logo">Auto Interview</h1>
        <button className="btn btn-ghost" onClick={logout}>
          Sign out
        </button>
      </header>

      <main className="dashboard-main">
        <div className="dashboard-top-row">
          <h2>Projects</h2>
          <button
            className="btn btn-primary"
            onClick={() => navigate("/projects/new")}
          >
            + Create Project
          </button>
        </div>

        {loading ? (
          <p className="muted-text">Loading projects...</p>
        ) : projects.length === 0 ? (
          <div className="empty-state">
            <p>No projects yet. Create your first interview project to get started.</p>
          </div>
        ) : (
          <div className="project-grid">
            {projects.map((p) => (
              <div
                key={p.id}
                className="project-card"
                onClick={() => navigate(`/projects/${p.id}`)}
              >
                <h3 className="project-card-name">{p.name}</h3>
                <div className="project-card-meta">
                  <span className="badge">{p.language.toUpperCase()}</span>
                  <span>{p.question_count} questions</span>
                </div>
                <p className="project-card-date">
                  {new Date(p.created_at).toLocaleDateString()}
                </p>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

/* ---------- Create Project Form ---------- */

function CreateProjectForm({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("en");
  const [researchObjective, setResearchObjective] = useState("");
  const [mode, setMode] = useState<"manual" | "csv">("manual");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [questions, setQuestions] = useState<QuestionCreate[]>([
    {
      section_index: 0,
      section_title: "Introduction",
      question_index: 0,
      main_question: "",
    },
  ]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function addQuestion() {
    setQuestions((prev) => [
      ...prev,
      {
        section_index: 0,
        section_title: "General",
        question_index: prev.length,
        main_question: "",
      },
    ]);
  }

  function updateQuestion(idx: number, value: string) {
    setQuestions((prev) =>
      prev.map((q, i) => (i === idx ? { ...q, main_question: value } : q))
    );
  }

  function removeQuestion(idx: number) {
    setQuestions((prev) => prev.filter((_, i) => i !== idx));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (mode === "csv" && csvFile) {
        await importProjectCSV(name, language, csvFile);
      } else {
        const validQuestions = questions.filter(
          (q) => q.main_question.trim() !== ""
        );
        await createProject({ name, language, research_objective: researchObjective || undefined, questions: validQuestions });
      }
      onCreated();
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to create project";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="create-form-card">
      <div className="create-form-header">
        <h3>New Project</h3>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>
          Cancel
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <form onSubmit={handleSubmit}>
        <label className="field-label">Project Name</label>
        <input
          type="text"
          className="field-input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Customer Feedback Q1"
          required
        />

        <label className="field-label">
          Research Objective <span className="muted-text">(optional)</span>
        </label>
        <textarea
          className="field-input"
          rows={3}
          value={researchObjective}
          onChange={(e) => setResearchObjective(e.target.value)}
          placeholder="e.g. Understand why customers churn after the first month and what job they were trying to get done"
        />

        <label className="field-label">Language</label>
        <select
          className="field-input"
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
        >
          {LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>

        <div className="mode-toggle">
          <button
            type="button"
            className={`mode-btn ${mode === "manual" ? "active" : ""}`}
            onClick={() => setMode("manual")}
          >
            Add questions manually
          </button>
          <button
            type="button"
            className={`mode-btn ${mode === "csv" ? "active" : ""}`}
            onClick={() => setMode("csv")}
          >
            Upload CSV
          </button>
        </div>

        {mode === "csv" ? (
          <div className="csv-upload">
            <input
              type="file"
              accept=".csv"
              onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
            />
            <p className="hint-text">
              CSV with columns: section_title, main_question, interview_notes,
              desired_learning
            </p>
          </div>
        ) : (
          <div className="questions-list">
            {questions.map((q, i) => (
              <div key={i} className="question-row">
                <input
                  type="text"
                  className="field-input"
                  value={q.main_question}
                  onChange={(e) => updateQuestion(i, e.target.value)}
                  placeholder={`Question ${i + 1}`}
                />
                {questions.length > 1 && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-danger-text"
                    onClick={() => removeQuestion(i)}
                  >
                    Remove
                  </button>
                )}
              </div>
            ))}
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={addQuestion}
            >
              + Add question
            </button>
          </div>
        )}

        <button
          type="submit"
          className="btn btn-primary btn-block"
          disabled={submitting}
        >
          {submitting ? "Creating..." : "Create Project"}
        </button>
      </form>
    </div>
  );
}
