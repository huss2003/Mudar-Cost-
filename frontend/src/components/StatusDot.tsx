export type DotVariant = 'idle' | 'active' | 'pending' | 'error' | 'success' | 'warn';

const VARIANT: Record<DotVariant, string> = {
  idle: 'dot',
  active: 'dot dot-active',
  success: 'dot dot-active',
  pending: 'dot dot-pending',
  warn: 'dot dot-pending',
  error: 'dot dot-error',
};

export default function StatusDot({ variant, title }: { variant: DotVariant; title?: string }) {
  return <span className={VARIANT[variant]} title={title} aria-label={title} />;
}
