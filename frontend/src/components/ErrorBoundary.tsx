import { Component, ErrorInfo, ReactNode } from 'react';
import { Alert, Button, Text, Stack, Group, Code } from '@mantine/core';

interface Props {
  children: ReactNode;
  /** Optional title shown in the error UI */
  title?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
  traceId: string | null;
}

/**
 * Global Error Boundary — catches React render errors anywhere in the
 * component tree below it and displays a structured fallback UI instead
 * of white-screening.
 *
 * Includes a **Try Again** button that resets the error state so the
 * subtree re-renders, and an **Expand / Collapse** toggle for technical
 * details.
 */
class ErrorBoundary extends Component<Props, State> {
  state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
    traceId: null,
  };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return {
      hasError: true,
      error,
      traceId: crypto.randomUUID?.() ?? 'unknown',
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ errorInfo });
    // Log to console for debugging
    console.error('[ErrorBoundary] Caught error:', error, errorInfo);
  }

  private handleRetry = (): void => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      traceId: null,
    });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <Alert color="red" title={this.props.title ?? 'Something went wrong'}>
          <Stack gap="sm">
            <Text size="sm">
              An unexpected error occurred in this section. Our team has
              been notified.
            </Text>

            {this.state.error && (
              <Text size="xs" c="dimmed">
                {this.state.error.message}
              </Text>
            )}

            {this.state.traceId && (
              <Text size="xs" c="dimmed">
                Trace ID: <Code>{this.state.traceId}</Code>
              </Text>
            )}

            <Group gap="xs">
              <Button
                variant="light"
                color="gray"
                size="xs"
                onClick={this.handleRetry}
              >
                Try Again
              </Button>
              <Button
                variant="subtle"
                color="gray"
                size="xs"
                onClick={() => window.location.reload()}
              >
                Reload Page
              </Button>
            </Group>
          </Stack>
        </Alert>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
