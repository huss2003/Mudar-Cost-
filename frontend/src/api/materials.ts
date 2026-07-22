import client from './client';
import type { Material, MaterialOption } from '../types';

export async function fetchMaterialsCatalog(opts?: {
  q?: string;
  category?: string;
  limit?: number;
}): Promise<Material[]> {
  const { data } = await client.get<Material[]>('/materials', { params: opts });
  return data;
}

export async function fetchMaterialAlternatives(materialId: number): Promise<MaterialOption[]> {
  const { data } = await client.get<MaterialOption[]>(`/materials/${materialId}/alternatives`);
  return data;
}
