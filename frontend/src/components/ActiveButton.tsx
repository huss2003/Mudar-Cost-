import type { CSSProperties, ReactNode } from 'react';

interface NavButtonProps {
  active: boolean;
  onClick?: () => void;
  type?: 'button' | 'submit';
  children: ReactNode;
  style?: CSSProperties;
  className?: string;
}

/**
 * Single source of truth for the "accent with hard shadow" button used by the sidebar,
 * drawing rows, version chips, etc.
 */
export default function ActiveButton({ active, onClick, type = 'button', children, style, className }: NavButtonProps) {
  return (
    <button
      type={type}
      onClick={onClick}
      className={className}
      style={{
        background: active ? 'var(--accent)' : 'transparent',
        color: active ? 'var(--accent-ink)' : 'var(--ink)',
        border: '1px solid',
        borderColor: active ? 'var(--ink)' : 'var(--rule-strong)',
        boxShadow: active ? '2px 2px 0 0 var(--ink)' : 'none',
        transition: 'all var(--t-fast) var(--ease)',
        fontFamily: 'inherit',
        ...style,
      }}
    >
      {children}
    </button>
  );
}
