import client from './client';
import type { Drawing, DetectedObject } from '../types';

export async function fetchDrawings(): Promise<Drawing[]> {
  const response = await client.get('/drawings');
  return response.data;
}

export async function fetchDrawingObjects(drawingId: number): Promise<DetectedObject[]> {
  const response = await client.get(`/drawings/${drawingId}/objects`);
  return response.data;
}
