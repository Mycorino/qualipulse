interface SkeletonProps {
  width?: string;
  height?: string;
  className?: string;
  lines?: number;
}

export function Skeleton({ width = "100%", height = "16px", className = "" }: SkeletonProps) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}

export function SkeletonCard() {
  return (
    <div className="skeleton-card">
      <Skeleton height="20px" width="60%" />
      <Skeleton height="14px" width="40%" />
      <Skeleton height="14px" width="80%" />
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="skeleton-table">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton-row">
          <Skeleton height="14px" width="25%" />
          <Skeleton height="14px" width="15%" />
          <Skeleton height="14px" width="20%" />
          <Skeleton height="14px" width="10%" />
        </div>
      ))}
    </div>
  );
}
