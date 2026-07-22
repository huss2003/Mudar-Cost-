import client from './client';
import type {
  AnomalyResponse,
  AskResponse,
  MissingBOQResponse,
  VEResponse,
} from '../types';

export async function aiAsk(projectId: number, question: string): Promise<AskResponse> {
  const { data } = await client.post<AskResponse>(`/projects/${projectId}/ai/ask`, { question });
  return data;
}

export async function aiMissingBOQ(projectId: number): Promise<MissingBOQResponse> {
  const { data } = await client.post<MissingBOQResponse>(`/projects/${projectId}/ai/missing-boq`);
  return data;
}

export async function aiAnomalies(projectId: number): Promise<AnomalyResponse> {
  const { data } = await client.post<AnomalyResponse>(`/projects/${projectId}/ai/anomalies`);
  return data;
}

export async function aiValueEngineering(projectId: number): Promise<VEResponse> {
  const { data } = await client.post<VEResponse>(`/projects/${projectId}/ai/value-engineering`);
  return data;
}

export async function aiCapabilities() {
  const { data } = await client.get('/ai/capabilities');
  return data;
}

export async function aiExtract(drawingId: number) {
  const { data } = await client.post('/ai/extract', { drawing_id: drawingId });
  return data;
}
