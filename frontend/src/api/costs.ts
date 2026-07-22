import client from './client';
import type { CostVersionSummary, TradeCostGroup } from '../types';

export async function fetchCostSummary(projectId: number): Promise<{ total: number; trades: TradeCostGroup[] }> {
  const { data } = await client.get(`/projects/${projectId}/cost-summary`);
  return data;
}

export async function fetchCostVersions(projectId: number): Promise<CostVersionSummary[]> {
  const { data } = await client.get<CostVersionSummary[]>(`/projects/${projectId}/cost-versions`);
  return data;
}

export async function fetchCostEstimate(estimateId: string) {
  const { data } = await client.get(`/cost-estimates/${estimateId}`);
  return data;
}

export async function listCostEstimates() {
  const { data } = await client.get('/cost-estimates');
  return data;
}
