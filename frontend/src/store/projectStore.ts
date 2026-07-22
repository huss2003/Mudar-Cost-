import { create } from 'zustand';
import { selectMaterial as apiSelectMaterial, fetchMaterials as apiFetchMaterials } from '../api/boq';
import { connectProjectLive } from '../api/sse';
import type {
  DetectedObject,
  MaterialOption,
  BOQLineItem,
  FinishPreset,
  Project,
} from '../types';

export type ViewMode = 'plan' | 'quantities' | 'materials' | 'costs' | 'ai' | 'export';
export const VIEW_IDS: readonly ViewMode[] = ['plan', 'quantities', 'materials', 'costs', 'ai', 'export'];

interface ProjectState {
  currentProject: Project | null;
  setCurrentProject: (p: Project | null) => void;
  drawingId: number | null;
  setDrawingId: (id: number | null) => void;
  detectedObjects: DetectedObject[];
  setDetectedObjects: (o: DetectedObject[]) => void;
  selectedObjectId: number | null;
  selectedObject: DetectedObject | null;
  selectObject: (id: number | null) => void;
  materialOptions: MaterialOption[];
  setMaterialOptions: (m: MaterialOption[]) => void;
  selectedMaterialId: number | null;
  selectMaterial: (boqItemId: number, materialId: number) => Promise<void>;
  boqItems: BOQLineItem[];
  setBoqItems: (b: BOQLineItem[]) => void;
  sseConnected: boolean;
  connectSSE: (projectId: number) => void;
  disconnectSSE: () => void;
  viewMode: ViewMode;
  setViewMode: (m: ViewMode) => void;
  finishPreset: FinishPreset;
  setFinishPreset: (p: FinishPreset) => void;
  loading: boolean;
  error: string | null;
  setError: (e: string | null) => void;
}

/** SSE handle stored outside the store but linked to a single live subscription. */
let liveHandle: { close: () => void } | null = null;

export const useProjectStore = create<ProjectState>((set, get) => ({
  currentProject: null,
  setCurrentProject: (p) => {
    if (p?.id !== get().currentProject?.id) {
      get().disconnectSSE();
      set({
        currentProject: p,
        drawingId: null, detectedObjects: [], boqItems: [],
        selectedObjectId: null, selectedObject: null,
        materialOptions: [], selectedMaterialId: null,
      });
      if (p) get().connectSSE(p.id);
    } else {
      set({ currentProject: p });
    }
  },

  drawingId: null,
  setDrawingId: (id: number | null) => set({ drawingId: id }),
  detectedObjects: [],
  setDetectedObjects: (o: DetectedObject[]) => set({ detectedObjects: o }),

  selectedObjectId: null,
  selectedObject: null,
  selectObject: (id) => {
    const obj = id !== null ? get().detectedObjects.find((o) => o.id === id) ?? null : null;
    set({ selectedObjectId: id, selectedObject: obj, materialOptions: [], selectedMaterialId: null });
  },

  materialOptions: [],
  setMaterialOptions: (m: MaterialOption[]) => set({ materialOptions: m }),
  selectedMaterialId: null,
  selectMaterial: async (boqItemId, materialId) => {
    set({ selectedMaterialId: materialId, loading: true, error: null });
    try {
      await apiSelectMaterial(boqItemId, materialId);
      const refreshed = await apiFetchMaterials(boqItemId);
      set({ materialOptions: refreshed, loading: false });
    } catch (err: any) {
      set({ selectedMaterialId: null, loading: false, error: err?.message ?? 'Failed to select material' });
    }
  },

  boqItems: [],
  setBoqItems: (b: BOQLineItem[]) => set({ boqItems: b }),

  sseConnected: false,
  connectSSE: (projectId) => {
    liveHandle?.close();
    liveHandle = connectProjectLive(projectId, {
      onConnected: () => set({ sseConnected: true }),
      onMaterialChanged: (data) => {
        const items = get().boqItems.map((i) =>
          i.id === data.boq_item_id
            ? { ...i, total: data.total ?? i.total, rate: data.rate ?? i.rate, material_name: data.material_name ?? i.material_name }
            : i,
        );
        set({ boqItems: items });
      },
      onError: () => set({ sseConnected: false }),
    });
  },
  disconnectSSE: () => {
    liveHandle?.close();
    liveHandle = null;
    set({ sseConnected: false });
  },

  viewMode: 'plan',
  setViewMode: (m: ViewMode) => set({ viewMode: m }),
  finishPreset: 'modern',
  setFinishPreset: (p: FinishPreset) => set({ finishPreset: p }),

  loading: false,
  error: null,
  setError: (e: string | null) => set({ error: e }),
}));

/** Derived selector — single source of truth for the running total. */
export const selectProjectTotal = (s: ProjectState): number =>
  s.boqItems.reduce((sum, it) => sum + (it.total ?? 0), 0);
