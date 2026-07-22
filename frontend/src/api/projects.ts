import client from './client';
import type { Project } from '../types';

/* ── Projects ─────────────────────────────────────────────────────── */

export async function fetchProjects(): Promise<Project[]> {
  const { data } = await client.get<Project[]>('/projects');
  return data;
}

export async function createProject(payload: {
  name: string;
  client?: string;
  location?: string;
}): Promise<Project> {
  const { data } = await client.post<Project>('/projects', payload);
  return data;
}

export async function fetchProject(projectId: number): Promise<Project> {
  const { data } = await client.get<Project>(`/projects/${projectId}`);
  return data;
}
