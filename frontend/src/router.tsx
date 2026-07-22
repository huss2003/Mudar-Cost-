import { createBrowserRouter, Navigate } from 'react-router-dom';
import Shell from './components/Shell';
import ProjectsIndex from './pages/ProjectsIndex';
import Workspace from './pages/Workspace';
import NotFound from './pages/NotFound';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Shell />,
    children: [
      { index: true, element: <Navigate to="/projects" replace /> },
      { path: 'projects', element: <ProjectsIndex /> },
      { path: 'projects/:projectId/*', element: <Workspace /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]);
