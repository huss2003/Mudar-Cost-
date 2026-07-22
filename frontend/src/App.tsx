import { RouterProvider } from 'react-router-dom';
import { MantineProvider, createTheme } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { router } from './router';
import ErrorBoundary from './components/ErrorBoundary';

const theme = createTheme({
  primaryColor: 'accent',
  colors: {
    accent: [
      '#eef0ff', '#d9ddff', '#b3b9ff', '#8c93ff', '#5e6ad2',
      '#5e6ad2', '#4d58b0', '#3d4790', '#2d3570', '#1d2350',
    ],
    dark: [
      '#C1C2C5', '#A6A7AB', '#909296', '#5C5F66', '#373A40',
      '#2C2E33', '#1a1b1e', '#131416', '#0d0e10', '#08090a',
    ],
  },
  primaryShade: { light: 5, dark: 5 },
  fontFamily: '-apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif',
  fontFamilyMonospace: 'ui-monospace, "SF Mono", "SF Mono", Menlo, Consolas, monospace',
  defaultRadius: 'md',
  black: '#08090a',
  white: '#f7f8f8',
  components: {
    Card: {
      defaultProps: {
        padding: 'lg',
        radius: 'lg',
      },
      styles: {
        root: {
          background: '#131416',
          border: '1px solid rgba(255,255,255,0.06)',
          transition: 'all 250ms cubic-bezier(0.4, 0, 0.2, 1)',
        },
      },
    },
    Paper: {
      defaultProps: {
        radius: 'lg',
      },
      styles: {
        root: {
          background: '#131416',
          border: '1px solid rgba(255,255,255,0.06)',
        },
      },
    },
    Button: {
      defaultProps: {
        radius: 'md',
      },
      styles: {
        root: {
          fontWeight: 600,
          transition: 'all 150ms cubic-bezier(0.4, 0, 0.2, 1)',
          '&:active': { transform: 'scale(0.97)' },
        },
      },
    },
    Input: {
      styles: {
        input: {
          background: '#0d0e10',
          borderColor: 'rgba(255,255,255,0.06)',
          color: '#f7f8f8',
          '&:focus': {
            borderColor: '#5e6ad2',
            boxShadow: '0 0 0 2px rgba(94,106,210,0.25)',
          },
        },
      },
    },
    NavLink: {
      styles: {
        root: {
          borderRadius: '10px',
          transition: 'all 150ms cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': { background: 'rgba(255,255,255,0.04)' },
          '&[data-active="true"]': {
            background: 'rgba(94,106,210,0.12)',
            '& .mantine-NavLink-label': { color: '#5e6ad2', fontWeight: 600 },
          },
        },
      },
    },
    Badge: {
      styles: {
        root: { fontWeight: 600 },
      },
    },
    Table: {
      styles: {
        th: {
          color: '#8b8d97',
          fontSize: '11px',
          fontWeight: 600,
          textTransform: 'uppercase' as const,
          letterSpacing: '0.05em',
          background: '#0d0e10',
        },
        td: {
          borderColor: 'rgba(255,255,255,0.04)',
        },
      },
    },
  },
});

export default function App() {
  return (
    <ErrorBoundary title="App Crashed">
      <MantineProvider theme={theme} defaultColorScheme="dark">
        <Notifications />
        <RouterProvider router={router} />
      </MantineProvider>
    </ErrorBoundary>
  );
}
