import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Container,
  Paper,
  Title,
  Text,
  Loader,
  Center,
  Box,
  Button,
} from '@mantine/core';
import { useAuthStore } from '../store/auth';

export default function Login() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState('');
  const [isExchanging, setIsExchanging] = useState(false);

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const loginWithKeycloak = useAuthStore((s) => s.loginWithKeycloak);
  const loginUrl = useAuthStore((s) => s.loginUrl);

  // Determine the redirect URI that was used (or should be used)
  const redirectUri =
    import.meta.env.VITE_KEYCLOAK_REDIRECT_URI ||
    window.location.origin + '/login';

  useEffect(() => {
    // If already authenticated, redirect to drawings
    if (isAuthenticated) {
      navigate('/drawings', { replace: true });
      return;
    }

    const code = searchParams.get('code');

    if (code) {
      // We have an auth code from Keycloak — exchange it for tokens
      setIsExchanging(true);
      setError('');

      loginWithKeycloak(code, redirectUri)
        .then(() => {
          navigate('/drawings', { replace: true });
        })
        .catch((err: Error) => {
          console.error('Token exchange failed:', err);
          setError(
            'Failed to complete login. Your session may have expired. Please try again.',
          );
        })
        .finally(() => {
          setIsExchanging(false);
        });
    }
    // If no code and not authenticated, wait for user to click "Sign in"
  }, [searchParams, isAuthenticated, loginWithKeycloak, navigate, redirectUri]);

  const handleSignIn = () => {
    window.location.href = loginUrl;
  };

  // If exchanging the code, show loading
  if (isExchanging) {
    return (
      <Box
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          background: 'linear-gradient(135deg, #1a1b2e 0%, #2c2e4a 100%)',
        }}
      >
        <Container size={420} py="xl">
          <Paper withBorder shadow="md" p="xl" radius="md" ta="center">
            <Center mb="md">
              <Loader size="lg" />
            </Center>
            <Title order={3} mb="xs">
              Completing sign in…
            </Title>
            <Text c="dimmed" size="sm">
              Exchanging credentials with Keycloak.
            </Text>
          </Paper>
        </Container>
      </Box>
    );
  }

  // If there's an error after exchange attempt
  if (error) {
    return (
      <Box
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          background: 'linear-gradient(135deg, #1a1b2e 0%, #2c2e4a 100%)',
        }}
      >
        <Container size={420} py="xl">
          <Paper withBorder shadow="md" p="xl" radius="md" ta="center">
            <Title order={3} mb="xs" c="red">
              Login Failed
            </Title>
            <Text c="dimmed" size="sm" mb="lg">
              {error}
            </Text>
            <Button fullWidth onClick={handleSignIn}>
              Try Again
            </Button>
          </Paper>
        </Container>
      </Box>
    );
  }

  // Default: show the login page with SSO button
  return (
    <Box
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        background: 'linear-gradient(135deg, #1a1b2e 0%, #2c2e4a 100%)',
      }}
    >
      <Container size={420} py="xl">
        <Title order={2} ta="center" c="white" mb="md">
          Auto Cost Engine
        </Title>
        <Text c="dimmed" size="sm" ta="center" mb="xl">
          Sign in with your organization account
        </Text>

        <Paper withBorder shadow="md" p="xl" radius="md" ta="center">
          <Text mb="md">
            This application uses Keycloak Single Sign-On (SSO) for
            authentication.
          </Text>
          <Button fullWidth size="lg" onClick={handleSignIn}>
            Sign in with Keycloak SSO
          </Button>
        </Paper>

        <Text c="dimmed" size="xs" ta="center" mt="md">
          Don&apos;t have an account?{' '}
          <Text component="span" c="blue" inherit>
            Contact your administrator
          </Text>
        </Text>
      </Container>
    </Box>
  );
}
