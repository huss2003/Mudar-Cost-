import { useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Center, Loader } from '@mantine/core';
import { useAuthStore } from '../store/auth';

interface AuthGuardProps {
  children: React.ReactNode;
}

export default function AuthGuard({ children }: AuthGuardProps) {
  const location = useLocation();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isInitialized = useAuthStore((s) => s.isInitialized);
  const setInitialized = useAuthStore((s) => s.setInitialized);

  useEffect(() => {
    if (!isInitialized) {
      // Check if we have persisted tokens
      const state = useAuthStore.getState();
      if (state.token && state.isAuthenticated) {
        // Already restored from localStorage via persist middleware
      }
      setInitialized();
    }
  }, [isInitialized, setInitialized]);

  if (!isInitialized) {
    return (
      <Center style={{ minHeight: '100vh' }}>
        <Loader size="lg" />
      </Center>
    );
  }

  if (!isAuthenticated) {
    // Redirect to login, preserving the intended destination
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
