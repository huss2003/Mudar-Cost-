import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div style={{ padding: '120px 64px', maxWidth: 720, margin: '0 auto' }}>
      <div className="kicker">Er · 404</div>
      <h1 className="display" style={{ fontSize: 96, lineHeight: 0.9, fontWeight: 500, marginTop: 12 }}>
        wrong<br /><em>filing cabinet.</em>
      </h1>
      <p style={{ marginTop: 20, color: 'var(--ink-2)', fontSize: 16 }}>
        The route you tried doesn't exist on this drawing. Step back to an index.
      </p>
      <Link to="/projects" className="btn btn-primary" style={{ marginTop: 24, display: 'inline-flex' }}>
        ← Back to projects
      </Link>
    </div>
  );
}
