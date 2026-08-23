/**
 * Small, dependency-free UI kit for the admin dashboard.
 * Styles live in ./admin.css under the .adm-* namespace.
 */
import { Fragment, useMemo, useState, type ReactNode } from "react";

// ── Formatting ────────────────────────────────────────────────────────────

export function fmtUsd(v: number | null | undefined, digits?: number): string {
  if (v === null || v === undefined) return "-";
  const d = digits ?? (Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 1 ? 2 : 3);
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })}`;
}

export function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  return v.toLocaleString();
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "2-digit" });
}

export function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "-";
  const diff = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diff / 86_400_000);
  if (days < 1) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

export function pct(part: number, total: number): string {
  if (!total) return "0%";
  return `${Math.round((100 * part) / total)}%`;
}

// ── Window picker ─────────────────────────────────────────────────────────

export function WindowPicker({
  value,
  onChange,
  options,
  labels,
}: {
  value: number;
  onChange: (v: number) => void;
  options: number[];
  labels: (v: number) => string;
}) {
  return (
    <div className="adm-seg" role="group">
      {options.map((o) => (
        <button key={o} type="button" aria-pressed={o === value} onClick={() => onChange(o)}>
          {labels(o)}
        </button>
      ))}
    </div>
  );
}

// ── KPI tile ──────────────────────────────────────────────────────────────

export function Delta({ pct: p, invert }: { pct: number | null | undefined; invert?: boolean }) {
  if (p === null || p === undefined) return <span className="adm-delta adm-delta--flat">new</span>;
  if (Math.abs(p) < 0.05) return <span className="adm-delta adm-delta--flat">0%</span>;
  const good = invert ? p < 0 : p > 0;
  return (
    <span className={`adm-delta ${good ? "adm-delta--up" : "adm-delta--down"}`}>
      {p > 0 ? "▲" : "▼"} {Math.abs(p).toFixed(Math.abs(p) >= 10 ? 0 : 1)}%
    </span>
  );
}

export function Kpi({
  label,
  value,
  previous,
  changePct,
  foot,
  accent,
  invert,
  hint,
}: {
  label: string;
  value: string;
  previous?: string;
  changePct?: number | null;
  foot?: string;
  accent?: boolean;
  /** A drop is good (cost, churn). */
  invert?: boolean;
  hint?: string;
}) {
  return (
    <div className={`adm-kpi${accent ? " adm-kpi--accent" : ""}`} title={hint}>
      <div className="adm-kpi__label">{label}</div>
      <div className="adm-kpi__value">{value}</div>
      <div className="adm-kpi__foot">
        {changePct !== undefined && <Delta pct={changePct} invert={invert} />}
        {previous !== undefined && <span>vs {previous}</span>}
        {foot && <span>{foot}</span>}
      </div>
    </div>
  );
}

// ── Card ──────────────────────────────────────────────────────────────────

export function Card({
  title,
  sub,
  right,
  children,
  className,
}: {
  title?: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`adm-card${className ? ` ${className}` : ""}`}>
      {title && (
        <h3 className="adm-card__title">
          <span>{title}</span>
          {right && <span style={{ fontWeight: 400, fontSize: 12, color: "var(--text-muted)" }}>{right}</span>}
        </h3>
      )}
      {sub && <p className="adm-card__sub">{sub}</p>}
      {children}
    </div>
  );
}

// ── Bar chart ─────────────────────────────────────────────────────────────

export interface BarSeries {
  key: string;
  label: string;
  tone: "muted" | "primary" | "secondary";
  format?: (v: number) => string;
}

/**
 * Daily bars, dependency free.
 * - `stack` (default): series stack bottom-up; scaled to the tallest column total.
 * - `overlay`: each series is scaled to its own peak and drawn in front of the
 *   previous one (narrower), so a series with tiny absolute values (signups)
 *   stays readable next to a large one (interviews).
 */
export function BarChart({
  data,
  series,
  mode = "stack",
  height = 120,
}: {
  data: Array<Record<string, number | string>>;
  series: BarSeries[];
  mode?: "stack" | "overlay";
  height?: number;
}) {
  const peaks = useMemo(() => {
    const out: Record<string, number> = {};
    for (const s of series) out[s.key] = Math.max(1, ...data.map((d) => Number(d[s.key] ?? 0)));
    return out;
  }, [data, series]);
  const stackPeak = useMemo(
    () => Math.max(1, ...data.map((d) => series.reduce((sum, s) => sum + Number(d[s.key] ?? 0), 0))),
    [data, series],
  );
  if (!data.length) return <div className="adm-empty">No data in this window.</div>;
  const first = String(data[0].date ?? "");
  const last = String(data[data.length - 1].date ?? "");
  return (
    <div className="adm-chart">
      <div className="adm-chart__bars" style={{ height }}>
        {data.map((d) => {
          const title = [String(d.date), ...series.map((s) => `${s.label}: ${(s.format ?? String)(Number(d[s.key] ?? 0))}`)].join("\n");
          return (
            <div key={String(d.date)} className={`adm-chart__col${mode === "overlay" ? " adm-chart__col--overlay" : ""}`} title={title}>
              {mode === "stack"
                ? [...series].reverse().map((s) => {
                    const v = Number(d[s.key] ?? 0);
                    const h = v > 0 ? Math.max(2, (v / stackPeak) * height) : 0;
                    return <div key={s.key} className={`adm-chart__bar adm-chart__bar--${s.tone}`} style={{ height: h }} />;
                  })
                : series.map((s, i) => {
                    const v = Number(d[s.key] ?? 0);
                    const h = v > 0 ? Math.max(2, (v / peaks[s.key]) * height) : 0;
                    return (
                      <div
                        key={s.key}
                        className={`adm-chart__bar adm-chart__bar--${s.tone}`}
                        style={{ height: h, position: "absolute", bottom: 0, left: `${i * 20}%`, right: `${i * 20}%`, width: "auto", zIndex: i + 1 }}
                      />
                    );
                  })}
            </div>
          );
        })}
      </div>
      <div className="adm-chart__axis">
        <span>{first}</span>
        <span className="adm-legend">
          {series.map((s) => (
            <span key={s.key}>
              <i style={{ background: toneColor(s.tone) }} />
              {s.label}
            </span>
          ))}
        </span>
        <span>{last}</span>
      </div>
    </div>
  );
}

function toneColor(tone: BarSeries["tone"]): string {
  return tone === "muted" ? "var(--viz-neutral-soft)" : tone === "primary" ? "var(--viz-seq-4)" : "var(--viz-seq-2)";
}

// ── Stacked bar (composition) ─────────────────────────────────────────────

const STACK_COLORS = [
  "var(--viz-seq-5)",
  "var(--viz-seq-4)",
  "var(--viz-seq-3)",
  "var(--viz-seq-2)",
  "var(--viz-annotation)",
  "var(--viz-neutral)",
  "var(--viz-neutral-soft)",
];

export function StackBar({
  parts,
  format = (v) => fmtUsd(v),
}: {
  parts: Array<{ label: string; value: number }>;
  format?: (v: number) => string;
}) {
  const visible = parts.filter((p) => p.value > 0);
  const total = visible.reduce((s, p) => s + p.value, 0);
  if (!total) return <div className="adm-empty">Nothing yet.</div>;
  return (
    <div>
      <div className="adm-stack">
        {visible.map((p, i) => (
          <span key={p.label} style={{ width: `${(100 * p.value) / total}%`, background: STACK_COLORS[i % STACK_COLORS.length] }} title={`${p.label}: ${format(p.value)}`} />
        ))}
      </div>
      <div className="adm-stack-legend">
        {visible.map((p, i) => (
          <Fragment key={p.label}>
            <span className="k"><i style={{ background: STACK_COLORS[i % STACK_COLORS.length] }} />{p.label}</span>
            <span className="v">{format(p.value)}</span>
            <span className="p">{pct(p.value, total)}</span>
          </Fragment>
        ))}
      </div>
    </div>
  );
}

// ── Funnel ────────────────────────────────────────────────────────────────

export function Funnel({ steps }: { steps: Array<{ label: string; count: number }> }) {
  const top = Math.max(1, steps[0]?.count ?? 0);
  return (
    <div className="adm-funnel">
      {steps.map((s, i) => {
        const prev = i > 0 ? steps[i - 1].count : null;
        return (
          <div key={s.label} className="adm-funnel__row">
            <span>{s.label}</span>
            <div className="adm-funnel__bar"><span style={{ width: `${(100 * s.count) / top}%` }} /></div>
            <span className="adm-funnel__n">
              {fmtInt(s.count)}
              {prev !== null && <small>{pct(s.count, prev)}</small>}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Sortable table ────────────────────────────────────────────────────────

export interface Column<T> {
  key: string;
  label: string;
  num?: boolean;
  sortable?: boolean;
  /** Render the cell; default prints the field. */
  render?: (row: T) => ReactNode;
  /** Value used for sorting + inline bar; default reads row[key]. */
  value?: (row: T) => number | string | null | undefined;
  /** Draw a faint bar behind the cell proportional to the column max. */
  bar?: boolean;
  width?: number | string;
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  onRowClick,
  defaultSort,
  empty = "Nothing to show.",
  limit,
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  defaultSort?: { key: string; dir: "asc" | "desc" };
  empty?: string;
  limit?: number;
}) {
  const [sort, setSort] = useState(defaultSort ?? null);
  const [showAll, setShowAll] = useState(false);

  const valueOf = (c: Column<T>, r: T) => (c.value ? c.value(r) : (r as Record<string, unknown>)[c.key] as number | string | null | undefined);

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col) return rows;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = valueOf(col, a);
      const vb = valueOf(col, b);
      if (va === vb) return 0;
      if (va === null || va === undefined) return 1;
      if (vb === null || vb === undefined) return -1;
      return (va > vb ? 1 : -1) * dir;
    });
  }, [rows, sort, columns]);

  const maxes = useMemo(() => {
    const out: Record<string, number> = {};
    for (const c of columns) {
      if (!c.bar) continue;
      out[c.key] = Math.max(0, ...rows.map((r) => Number(valueOf(c, r) ?? 0)));
    }
    return out;
  }, [rows, columns]);

  const visible = limit && !showAll ? sorted.slice(0, limit) : sorted;

  if (!rows.length) return <div className="adm-empty">{empty}</div>;
  return (
    <div className="adm-table-wrap">
      <table className="adm-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                className={`${c.num ? "num" : ""} ${c.sortable ? "sortable" : ""}`}
                style={c.width ? { width: c.width } : undefined}
                onClick={c.sortable ? () => setSort((s) => ({ key: c.key, dir: s?.key === c.key && s.dir === "desc" ? "asc" : "desc" })) : undefined}
              >
                {c.label}
                {sort?.key === c.key && <span className="arrow">{sort.dir === "desc" ? "▼" : "▲"}</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visible.map((r) => (
            <tr key={rowKey(r)} className={onRowClick ? "clickable" : undefined} onClick={onRowClick ? () => onRowClick(r) : undefined}>
              {columns.map((c) => {
                const v = valueOf(c, r);
                const content = c.render ? c.render(r) : (v ?? "-");
                if (c.bar && maxes[c.key] > 0) {
                  const w = (100 * Number(v ?? 0)) / maxes[c.key];
                  return (
                    <td key={c.key} className={`bar-cell ${c.num ? "num" : ""}`}>
                      <i style={{ width: `${w}%`, ...(c.num ? { left: "auto", right: 0 } : {}) }} />
                      <span>{content}</span>
                    </td>
                  );
                }
                return <td key={c.key} className={c.num ? "num" : undefined}>{content}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {limit && sorted.length > limit && (
        <div style={{ marginTop: 8 }}>
          <button type="button" className="adm-link" onClick={() => setShowAll((s) => !s)}>
            {showAll ? "Show fewer" : `Show all ${sorted.length}`}
          </button>
        </div>
      )}
    </div>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────

export function Skeleton({ h = 120 }: { h?: number }) {
  return <div className="adm-skel" style={{ height: h }} />;
}

// ── Drawer ────────────────────────────────────────────────────────────────

export function Drawer({ title, sub, onClose, children }: { title: ReactNode; sub?: ReactNode; onClose: () => void; children: ReactNode }) {
  return (
    <>
      <div className="adm-drawer-backdrop" onClick={onClose} />
      <aside className="adm-drawer" role="dialog" aria-modal="true">
        <div className="adm-drawer__head">
          <div>
            <h3>{title}</h3>
            {sub && <p>{sub}</p>}
          </div>
          <button type="button" className="adm-drawer__close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="adm-drawer__body">{children}</div>
      </aside>
    </>
  );
}
