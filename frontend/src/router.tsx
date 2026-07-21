import { createBrowserRouter, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import AuthGuard from './components/AuthGuard';
import Drawings from './pages/Drawings';
import Quantities from './pages/Quantities';
import Materials from './pages/Materials';
import Costs from './pages/Costs';
import AI from './pages/AI';
import Exports from './pages/Exports';
import Login from './pages/Login';

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/',
    element: (
      <AuthGuard>
        <Layout />
      </AuthGuard>
    ),
    children: [
      {
        index: true,
        element: <Navigate to="/drawings" replace />,
      },
      {
        path: 'drawings',
        element: <Drawings />,
      },
      {
        path: 'quantities',
        element: <Quantities />,
      },
      {
        path: 'materials',
        element: <Materials />,
      },
      {
        path: 'costs',
        element: <Costs />,
      },
      {
        path: 'ai',
        element: <AI />,
      },
      {
        path: 'exports',
        element: <Exports />,
      },
    ],
  },
]);
