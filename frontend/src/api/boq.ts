import client from './client';
import type { BOQLineItem, BOQResponse, BOQSummaryResponse, MaterialOption } from '../types';

export async function fetchBOQ(projectId: number): Promise<BOQResponse> {
  const { data } = await client.get<BOQResponse>(`/projects/${projectId}/boq`);
  return data;
}

export async function computeQuantities(projectId: number): Promise<{ task_id: string; status: string }> {
  const { data } = await client.post(`/projects/${projectId}/compute-quantities`);
  return data;
}

export async function fetchMaterials(boqItemId: number): Promise<MaterialOption[]> {
  // Backend route: GET /boq-items/{id}/materials  → list of options
  const { data } = await client.get<MaterialOption[]>(`/boq-items/${boqItemId}/materials`);
  return data;
}

export async function selectMaterial(boqItemId: number, materialId: number): Promise<void> {
  await client.post(`/boq-items/${boqItemId}/select-material`, { material_id: materialId });
}

export async function fetchSummary(projectId: number): Promise<BOQSummaryResponse> {
  const { data } = await client.get<BOQSummaryResponse>(`/projects/${projectId}/summary`);
  return data;
}

export async function updateBoqItem(
  itemId: number,
  fields: Partial<Pick<BOQLineItem, 'quantity' | 'rate' | 'total'>>,
): Promise<BOQLineItem> {
  const { data } = await client.patch<BOQLineItem>(`/boq-items/${itemId}`, fields);
  return data;
}
