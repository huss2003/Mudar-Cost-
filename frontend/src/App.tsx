import { RouterProvider } from 'react-router-dom';
import { MantineProvider, createTheme } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { router } from './router';
import ErrorBoundary from './components/ErrorBoundary';

const theme = createTheme({
  primaryColor: 'blue',
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif',
  defaultRadius: 'md',
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
