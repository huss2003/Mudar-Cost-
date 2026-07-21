// Mock browser APIs that are missing in jsdom environment

// Mock MatchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// Mock ResizeObserver
class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  value: MockResizeObserver,
});

// Mock IntersectionObserver
class MockIntersectionObserver {
  readonly root: Element | null = null;
  readonly rootMargin: string = '';
  readonly thresholds: ReadonlyArray<number> = [];

  constructor() {}

  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}
Object.defineProperty(window, 'IntersectionObserver', {
  writable: true,
  value: MockIntersectionObserver,
});

// Mock EventSource
class MockEventSource {
  readonly url: string;
  readonly withCredentials: boolean;
  private listeners: Map<string, Set<(event: MessageEvent) => void>> = new Map();
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  readyState: number = 0;
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;

  constructor(url: string, eventSourceInitDict?: { withCredentials?: boolean }) {
    this.url = url;
    this.withCredentials = eventSourceInitDict?.withCredentials ?? false;
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)!.add(listener);
  }

  removeEventListener(type: string, listener: (event: MessageEvent) => void) {
    this.listeners.get(type)?.delete(listener);
  }

  dispatchEvent(event: Event): boolean {
    return true;
  }

  close() {
    this.readyState = 2; // CLOSED
    this.listeners.clear();
    if (this.onerror) {
      this.onerror(new Event('error'));
    }
  }
}
Object.defineProperty(window, 'EventSource', {
  writable: true,
  value: MockEventSource,
});

// Mock console methods to avoid noise
const originalConsoleWarn = console.warn;
const originalConsoleError = console.error;

// Suppress specific console messages during tests
afterEach(() => {
  console.warn = originalConsoleWarn;
  console.error = originalConsoleError;
});
