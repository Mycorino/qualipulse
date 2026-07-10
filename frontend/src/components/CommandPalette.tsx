import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import type { StudySummary } from "../api/studies";

/**
 * CommandPalette — ⌘K quick-switcher for the research hub.
 *
 * Deliberately dependency-free and deterministic: plain substring match
 * over study names plus a fixed action list. The parent owns the open
 * state (the global ⌘K listener lives here so every hub surface gets the
 * shortcut for free once mounted).
 */

interface PaletteCommand {
  id: string;
  group: "studies" | "actions";
  label: string;
  hint?: string;
  run: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onOpen: () => void;
  studies: StudySummary[] | null;
  onNewStudy: () => void;
  onMemos?: () => void;
}

export function CommandPalette({ open, onClose, onOpen, studies, onNewStudy, onMemos }: CommandPaletteProps) {
  const { t } = useTranslation("dashboard");
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const commands = useMemo<PaletteCommand[]>(() => {
    const studyCmds: PaletteCommand[] = (studies ?? []).map((s) => ({
      id: `study-${s.id}`,
      group: "studies" as const,
      label: s.name,
      hint: s.has_report
        ? t("hub.palette.hintReport")
        : t("hub.palette.hintCounts", {
            interviews: s.completed_interview_count,
            responses: s.completed_response_count,
          }),
      run: () => navigate(`/studies/${s.id}`),
    }));
    const actionCmds: PaletteCommand[] = [
      { id: "new-study", group: "actions", label: t("hub.palette.newStudy"), run: onNewStudy },
      ...(onMemos
        ? [{ id: "memos", group: "actions" as const, label: t("hub.palette.memos"), run: onMemos }]
        : []),
      { id: "account", group: "actions", label: t("hub.palette.account"), run: () => navigate("/account") },
    ];
    return [...studyCmds, ...actionCmds];
  }, [studies, navigate, onNewStudy, onMemos, t]);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => c.label.toLowerCase().includes(q));
  }, [commands, query]);

  // Global shortcut: ⌘K / Ctrl+K toggles, Esc closes.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) onClose();
        else onOpen();
      } else if (open && e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose, onOpen]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setSel(0);
      // Focus after the panel mounts.
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  useEffect(() => {
    setSel(0);
  }, [query]);

  if (!open) return null;

  const runCommand = (cmd: PaletteCommand) => {
    onClose();
    cmd.run();
  };

  const onInputKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSel((v) => Math.min(v + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSel((v) => Math.max(v - 1, 0));
    } else if (e.key === "Enter" && matches[sel]) {
      e.preventDefault();
      runCommand(matches[sel]);
    }
  };

  let lastGroup: PaletteCommand["group"] | null = null;

  return (
    <>
      <div className="hub-palette__backdrop" onClick={onClose} />
      <div className="hub-palette" role="dialog" aria-modal="true" aria-label={t("hub.palette.aria")}>
        <div className="hub-palette__input">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
            <path d="m10.5 10.5 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            placeholder={t("hub.palette.placeholder")}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onInputKey}
            aria-label={t("hub.palette.placeholder")}
          />
        </div>
        <div className="hub-palette__list">
          {matches.length === 0 && <div className="hub-palette__group">{t("hub.palette.noResults")}</div>}
          {matches.map((cmd, i) => {
            const header =
              cmd.group !== lastGroup ? (
                <div key={`g-${cmd.group}`} className="hub-palette__group">
                  {t(`hub.palette.group.${cmd.group}`)}
                </div>
              ) : null;
            lastGroup = cmd.group;
            return (
              <div key={cmd.id}>
                {header}
                <button
                  type="button"
                  className={`hub-palette__item${i === sel ? " hub-palette__item--sel" : ""}`}
                  onMouseEnter={() => setSel(i)}
                  onClick={() => runCommand(cmd)}
                >
                  <span className="hub-palette__ic" aria-hidden="true">
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                      <path d="M6 3.5 10.5 8 6 12.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                  <span className="hub-palette__label">{cmd.label}</span>
                  {cmd.hint && <span className="hub-palette__hint">{cmd.hint}</span>}
                </button>
              </div>
            );
          })}
        </div>
        <div className="hub-palette__foot">
          <span>
            <kbd>↑↓</kbd> {t("hub.palette.navigate")}
          </span>
          <span>
            <kbd>↵</kbd> {t("hub.palette.select")}
          </span>
          <span>
            <kbd>esc</kbd> {t("hub.palette.close")}
          </span>
        </div>
      </div>
    </>
  );
}
