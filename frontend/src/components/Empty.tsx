import { ReactNode } from 'react';

export default function Empty({
  title,
  hint,
  children,
}: {
  title: ReactNode;
  hint?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div style={{ padding: '64px 0', textAlign: 'center' }}>
      <div className="display" style={{ fontSize: 32, fontStyle: 'italic', color: 'var(--ink-3)' }}>
        {title}
      </div>
      {hint && <div className="kicker" style={{ marginTop: 8 }}>{hint}</div>}
      {children}
    </div>
  );
}
