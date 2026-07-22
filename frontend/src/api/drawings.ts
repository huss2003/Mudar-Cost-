import client from './client';
import type {
  Drawing,
  DrawingStatusResponse,
  DrawingUploadResponse,
  DetectedObject,
} from '../types';

/* ── Drawings ─────────────────────────────────────────────────────── */

export async function fetchDrawings(projectId?: number): Promise<Drawing[]> {
  const { data } = await client.get<Drawing[]>('/drawings', {
    params: projectId ? { project_id: projectId } : undefined,
  });
  return data;
}

export async function uploadDrawing(
  file: File,
  projectId: number,
  onProgress?: (pct: number) => void,
): Promise<DrawingUploadResponse> {
  const fd = new FormData();
  fd.append('file', file);
  const { data } = await client.post<DrawingUploadResponse>('/drawings', fd, {
    params: { project_id: projectId },
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (e.total && onProgress) onProgress(Math.round((e.loaded * 100) / e.total));
    },
  });
  return data;
}

export async function fetchDrawingStatus(drawingId: number): Promise<DrawingStatusResponse> {
  const { data } = await client.get<DrawingStatusResponse>(`/drawings/${drawingId}/status`);
  return data;
}

export async function replaceDrawingFile(
  drawingId: number,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<DrawingUploadResponse> {
  const fd = new FormData();
  fd.append('file', file);
  const { data } = await client.put<DrawingUploadResponse>(`/drawings/${drawingId}`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (e.total && onProgress) onProgress(Math.round((e.loaded * 100) / e.total));
    },
  });
  return data;
}

export async function fetchDrawingObjects(drawingId: number): Promise<DetectedObject[]> {
  const { data } = await client.get<DetectedObject[]>(`/drawings/${drawingId}/objects`);
  return data;
}

export async function deleteDrawing(drawingId: number): Promise<void> {
  await client.delete(`/drawings/${drawingId}`);
}

export async function fetchObjectTypes(): Promise<{ key: string; label: string; family: string }[]> {
  const { data } = await client.get('/drawings/types');
  return data;
}
