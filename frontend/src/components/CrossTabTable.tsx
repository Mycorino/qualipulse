import { useTranslation } from "react-i18next";

/**
 * CrossTabTable — dense segment × theme table with conditional formatting.
 *
 * Each cell shows a percentage with a `--viz-seq-*` background tint scaled
 * to the value. Tabular numerals so columns line up. Row totals bolded.
 * Sticky header row when the table scrolls inside its parent.
 *
 * Honesty requirements baked in (per the methodologist):
 *   - Cells below `minN` show counts ("8/12") instead of percentages and
 *     get a muted background regardless of value (since the % is
 *     meaningless at small n).
 *   - Footer summarizes the table-level n + significance note.
 */

export interface CrossTabRow {
  label: string;
  /** Per-column values, must align with the `columns` array. Undefined = blank cell. */
  values: (number | undefined)[];
  /** Per-column counts, when below minN we display these instead of values. */
  counts?: (number | undefined)[];
}

interface CrossTabTableProps {
  /** Column headers, e.g. ["Promoters", "Passives", "Detractors"]. */
  columns: string[];
  rows: CrossTabRow[];
  /** Threshold below which we display counts not percentages. */
  minN?: number;
  /** Per-column total n, shown beneath the header. */
  columnNs?: number[];
  /** Optional table-level note appended in the footer. */
  note?: string;
}

export function CrossTabTable({
  columns,
  rows,
  minN = 30,
  columnNs,
  note,
}: CrossTabTableProps) {
  const { t } = useTranslation("study");
  const allValues = rows.flatMap((r) => r.values).filter((v): v is number => typeof v === "number");
  const max = Math.max(0, ...allValues);

  return (
    <div className="cross-tab" role="table" aria-label={t("crossTab.ariaLabel")}>
      <table className="cross-tab__table">
        <thead>
          <tr>
            <th className="cross-tab__row-header">{t("crossTab.themeHeader")}</th>
            {columns.map((col, i) => (
              <th key={col} className="cross-tab__column-header">
                <div>{col}</div>
                {columnNs && typeof columnNs[i] === "number" && (
                  <div className="cross-tab__column-n tabular">{t("crossTab.columnN", { count: columnNs[i] })}</div>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th className="cross-tab__row-name" scope="row">{row.label}</th>
              {row.values.map((value, i) => {
                const n = row.counts?.[i];
                // The methodologist's rule is about *segment* sample size
                // (the column's total n), not the cell count. A column with
                // n<30 can't reliably support percentages on any row.
                const columnN = columnNs?.[i];
                const smallN = typeof columnN === "number" && columnN < minN;
                if (typeof value !== "number") {
                  return <td key={i} className="cross-tab__cell cross-tab__cell--empty">{t("crossTab.empty")}</td>;
                }
                if (smallN) {
                  return (
                    <td
                      key={i}
                      className="cross-tab__cell cross-tab__cell--small-n tabular"
                      title={t("crossTab.smallNTitle", { columnN, minN })}
                    >
                      {typeof n === "number" ? `${n}/${columnN}` : t("crossTab.empty")}
                    </td>
                  );
                }
                const tint = pickTint(value, max);
                return (
                  <td
                    key={i}
                    className="cross-tab__cell tabular"
                    style={{ background: `var(--${tint})` }}
                  >
                    <span className={tint === "viz-seq-4" || tint === "viz-seq-5" ? "cross-tab__cell-strong" : undefined}>
                      {value}%
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {note && <p className="cross-tab__note">{note}</p>}
    </div>
  );
}

function pickTint(value: number, max: number): string {
  const r = max > 0 ? value / max : 0;
  if (r >= 0.8) return "viz-seq-5";
  if (r >= 0.6) return "viz-seq-4";
  if (r >= 0.4) return "viz-seq-3";
  if (r >= 0.2) return "viz-seq-2";
  return "viz-seq-1";
}
