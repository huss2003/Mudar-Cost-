interface SkeletonProps {
  rows?: number;
  columns?: number;
  variant?: 'row' | 'bar';
  widths?: number[];
}

export default function Skeleton({ rows = 4, columns = 6, variant = 'row', widths }: SkeletonProps) {
  return (
    <div style={{ paddingTop: variant === 'bar' ? 0 : 8 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          style={{
            display: 'grid',
            gridTemplateColumns: '60px 1.6fr 1fr 1fr 1fr 24px',
            gap: 16,
            alignItems: 'center',
            padding: '14px 4px',
            borderBottom: '1px solid var(--rule)',
          }}
        >
          {Array.from({ length: columns }).map((__, j) => (
            <div
              key={j}
              className="sk"
              style={{
                height: variant === 'bar' ? 12 : j === 1 ? 16 : 12,
                width: widths?.[j] ?? '80%',
              }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
