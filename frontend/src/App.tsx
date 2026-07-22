import { Component, ReactNode } from 'react';
import { RouterProvider } from 'react-router-dom';
import { router } from './router';

interface Props { children: ReactNode }
interface State { error: Error | null }

class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };
  static getDerivedStateFromError(error: Error): Partial<State> { return { error }; }
  reset = () => this.setState({ error: null });
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 48, fontFamily: 'var(--font-display)' }}>
          <h1 className="display" style={{ fontSize: 48, fontStyle: 'italic' }}>
            something went sideways.
          </h1>
          <p style={{ marginTop: 12, color: 'var(--brick)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            {this.state.error.message}
          </p>
          <button className="btn btn-primary" type="button" onClick={this.reset} style={{ marginTop: 16 }}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  return (
    <ErrorBoundary>
      <RouterProvider router={router} />
    </ErrorBoundary>
  );
}
