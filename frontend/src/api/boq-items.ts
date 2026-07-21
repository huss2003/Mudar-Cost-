import client from './client';
import type { Material } from '../types';

export async function fetchMaterials(boqItemId: number): Promise<Material[]> {
  const response = await client.get(`/boq-items/${boqItemId}/materials`);
  return response.data;
}

export async function selectMaterial(boqItemId: number, materialId: number): Promise<void> {
  await client.post(`/boq-items/${boqItemId}/select-material`, {
    material_id: materialId,
  });
}
