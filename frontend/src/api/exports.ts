import client from './client';

export async function generateProposal(projectId: number) {
  const { data } = await client.post(`/projects/${projectId}/proposal`);
  return data;
}

export async function generateExport(projectId: number, format: 'xlsx' | 'pdf') {
  const { data } = await client.post(`/projects/${projectId}/export`, { format });
  return data;
}

export async function generatePurchaseList(projectId: number) {
  const { data } = await client.post(`/projects/${projectId}/purchase-list`);
  return data;
}

export async function generateClientPresentation(projectId: number) {
  const { data } = await client.post(`/projects/${projectId}/client-presentation`);
  return data;
}

export async function listExports(projectId?: number) {
  const { data } = await client.get('/exports', { params: projectId ? { project_id: projectId } : undefined });
  return data;
}

export async function downloadExport(exportId: number): Promise<{ url: string; expires_in: number }> {
  const { data } = await client.get(`/exports/${exportId}/download`);
  return data;
}
