import { useTranslation } from "react-i18next";

/**
 * CompareChips — segment filter row at the top of a dashboard canvas.
 *
 * Multi-select. Brand-active state when a chip is on. Drives all chart-cards
 * below via the parent's filter state — this component is dumb display +
 * onChange. Grouped by dimension (e.g. "Role", "Region") so users don't have
 * to scan a flat soup of chips.
 *
 * Behavior rules from the design plan:
 *   - Clicking a selected chip deselects it.
 *   - "All" chip on each group resets that dimension to no filter.
 *   - Below n=30 in any single-chip subset, the dashboard surfaces a
 *     small-n warning automatically (handled by the parent reading `value`).
 */
export interface CompareChipsGroup {
  /** Dimension label, e.g. "Role". Rendered as an eyebrow above the chips. */
  dimension: string;
  /** Available options for this dimension. */
  options: { value: string; label: string; count?: number }[];
}

interface CompareChipsProps {
  groups: CompareChipsGroup[];
  /** Currently-selected values, keyed by dimension. */
  value: Record<string, string[]>;
  onChange: (next: Record<string, string[]>) => void;
}

export function CompareChips({ groups, value, onChange }: CompareChipsProps) {
  const { t } = useTranslation("study");
  const toggle = (dimension: string, optionValue: string) => {
    const current = value[dimension] ?? [];
    const next = current.includes(optionValue)
      ? current.filter((v) => v !== optionValue)
      : [...current, optionValue];
    onChange({ ...value, [dimension]: next });
  };

  const clearGroup = (dimension: string) => {
    const next = { ...value };
    delete next[dimension];
    onChange(next);
  };

  return (
    <div className="compare-chips" role="group" aria-label={t("compareChips.ariaLabel")}>
      {groups.map((group) => {
        const selected = value[group.dimension] ?? [];
        const isAll = selected.length === 0;
        return (
          <div key={group.dimension} className="compare-chips__group">
            <span className="compare-chips__label">{group.dimension}</span>
            <button
              type="button"
              className={`compare-chips__chip${isAll ? " compare-chips__chip--active" : ""}`}
              onClick={() => clearGroup(group.dimension)}
              aria-pressed={isAll}
            >
              {t("compareChips.all")}
            </button>
            {group.options.map((opt) => {
              const active = selected.includes(opt.value);
              return (
                <button
                  key={opt.value}
                  type="button"
                  className={`compare-chips__chip${active ? " compare-chips__chip--active" : ""}`}
                  onClick={() => toggle(group.dimension, opt.value)}
                  aria-pressed={active}
                >
                  {opt.label}
                  {typeof opt.count === "number" && (
                    <span className="compare-chips__count tabular">{opt.count}</span>
                  )}
                </button>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
