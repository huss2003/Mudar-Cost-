import { createBrowserRouter, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Drawings from './pages/Drawings';
import Quantities from './pages/Quantities';
import Materials from './pages/Materials';
import Costs from './pages/Costs';
import AI from './pages/AI';
import Exports from './pages/Exports';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
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
