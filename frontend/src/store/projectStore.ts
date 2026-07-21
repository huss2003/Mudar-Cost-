import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import client from '../api/client';

// ─── Data Types ───────────────────────────────────────────────────────────────

export interface DetectedObject {
  id: number;
  drawing_id: number;
  object_type: string;
  label: string | null;
  length: number | null;
  width: number | null;
  area: number | null;
  height: number | null;
  thickness: number | null;
  location_x: number | null;
  location_y: number | null;
  layer: string | null;
  confidence: number | null;
  bbox_coords: number[] | null;
}

export interface MaterialOption {
  material_id: number;
  name: string;
  brand: string;
  sku: string;
  rate: number;
  unit: string;
  gst_rate: number;
  vendor_name: string;
  lead_time_days: number;
  warranty: string | null;
  fire_rating: string | null;
  is_preferred: boolean;
}

export interface BOQItem {
  id: number;
  description: string;
  quantity: number;
  unit: string;
  rate: number;
  total: number;
  trade: string | null;
  material_name: string | null;
}

// ─── SSE Connection State (module-level, not in Zustand) ────────────────────

let eventSource: EventSource | null = null;
let reconnectTimeoutId: ReturnType<typeof setTimeout> | null = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_DELAY = 30_000; // 30-second ceiling

function getReconnectDelay(): number {
  const delay = Math.min(
    3_000 * 2 ** reconnectAttempts,
    MAX_RECONNECT_DELAY,
  );
  reconnectAttempts += 1;
  return delay;
}

function cleanupEventSource(resetAttempts: boolean): void {
  if (reconnectTimeoutId) {
    clearTimeout(reconnectTimeoutId);
    reconnectTimeoutId = null;
  }
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  if (resetAttempts) {
    reconnectAttempts = 0;
  }
}

// ─── Finish presets & view-mode literal helpers ─────────────────────────────

const VALID_FINISH_PRESETS = ['modern', 'industrial', 'luxury', 'minimal'] as const;
type FinishPreset = (typeof VALID_FINISH_PRESETS)[number];

const VALID_VIEW_MODES = ['2d', '3d', 'split'] as const;
type ViewMode = (typeof VALID_VIEW_MODES)[number];

// ─── State interface ─────────────────────────────────────────────────────────

export interface ProjectState {
  // Current project
  currentProjectId: number | null;
  setCurrentProject: (id: number) => void;

  // Detected objects for current drawing
  detectedObjects: DetectedObject[];
  setDetectedObjects: (objects: DetectedObject[]) => void;

  // Selected object (from 2D or 3D viewer)
  selectedObjectId: number | null;
  selectedObject: DetectedObject | null;
  selectObject: (id: number | null) => void;

  // Material options for selected object
  materialOptions: MaterialOption[];
  setMaterialOptions: (options: MaterialOption[]) => void;
  selectedMaterialId: number | null;
  selectMaterial: (materialId: number) => Promise<void>;

  // BOQ data
  boqItems: BOQItem[];
  setBoqItems: (items: BOQItem[]) => void;
  projectTotal: number;
  setProjectTotal: (total: number) => void;

  // UI state
  finishPreset: FinishPreset;
  setFinishPreset: (preset: string) => void;
  viewMode: ViewMode;
  setViewMode: (mode: string) => void;

  // Live updates via SSE
  sseConnected: boolean;
  connectSSE: (projectId: number) => void;
  disconnectSSE: () => void;

  // Loading / error
  loading: boolean;
  error: string | null;
}

// ─── Store ───────────────────────────────────────────────────────────────────

export const useProjectStore = create<ProjectState>()(
  devtools(
    (set, get) => ({
      // ── Project ────────────────────────────────────────────────────────
      currentProjectId: null,
      setCurrentProject: (id: number) => {
        // Tear down old connection
        get().disconnectSSE();

        // Reset all project-scoped state
        set({
          currentProjectId: id,
          detectedObjects: [],
          boqItems: [],
          selectedObjectId: null,
          selectedObject: null,
          materialOptions: [],
          selectedMaterialId: null,
          projectTotal: 0,
          loading: false,
          error: null,
        });

        // Wire up live updates for the new project
        get().connectSSE(id);
      },

      // ── Detected objects ───────────────────────────────────────────────
      detectedObjects: [],
      setDetectedObjects: (objects) => set({ detectedObjects: objects }),

      // ── Selection ──────────────────────────────────────────────────────
      selectedObjectId: null,
      selectedObject: null,
      selectObject: (id: number | null) => {
        if (id === null) {
          set({
            selectedObjectId: null,
            selectedObject: null,
            materialOptions: [],
            selectedMaterialId: null,
          });
          return;
        }
        const obj = get().detectedObjects.find((o) => o.id === id) ?? null;
        set({
          selectedObjectId: id,
          selectedObject: obj,
          // Clear old material selection when switching objects
          materialOptions: [],
          selectedMaterialId: null,
        });
      },

      // ── Material options & selection ───────────────────────────────────
      materialOptions: [],
      setMaterialOptions: (options) => set({ materialOptions: options }),

      selectedMaterialId: null,
      selectMaterial: async (materialId: number) => {
        const { selectedObject, boqItems } = get();
        if (!selectedObject) {
          set({ error: 'No object selected to assign a material to' });
          return;
        }

        // Determine which BOQ item this material selection targets.
        // Priority:  1) trade matches object_type
        //            2) first item with no material assigned yet
        //            3) first BOQ item as fallback
        let targetBoqItem: BOQItem | null =
          boqItems.find(
            (i) =>
              i.trade !== null &&
              selectedObject.object_type !== null &&
              i.trade.toLowerCase() === selectedObject.object_type.toLowerCase(),
          ) ?? null;

        if (!targetBoqItem) {
          targetBoqItem =
            boqItems.find((i) => i.material_name === null) ?? null;
        }
        if (!targetBoqItem && boqItems.length > 0) {
          targetBoqItem = boqItems[0];
        }
        if (!targetBoqItem) {
          set({ error: 'No BOQ item available to assign the material to' });
          return;
        }

        // Optimistic update
        set({ selectedMaterialId: materialId, loading: true, error: null });

        try {
          await client.post(`/boq-items/${targetBoqItem.id}/select-material`, {
            material_id: materialId,
          });

          // SSE will push the cost update asynchronously; we still
          // refetch material options so the panel shows "selected" state.
          const { data: freshOptions } = await client.get<MaterialOption[]>(
            `/boq-items/${targetBoqItem.id}/material-options`,
          );
          if (freshOptions) {
            set({ materialOptions: freshOptions, loading: false });
          } else {
            set({ loading: false });
          }
        } catch (err: any) {
          // Revert optimistic update
          set({
            selectedMaterialId: null,
            loading: false,
            error:
              err?.response?.data?.detail ??
              err.message ??
              'Failed to assign material',
          });
        }
      },

      // ── BOQ data ───────────────────────────────────────────────────────
      boqItems: [],
      setBoqItems: (items) => set({ boqItems: items }),

      projectTotal: 0,
      setProjectTotal: (total) => set({ projectTotal: total }),

      // ── UI state ───────────────────────────────────────────────────────
      finishPreset: 'modern',
      setFinishPreset: (preset: string) => {
        if ((VALID_FINISH_PRESETS as readonly string[]).includes(preset)) {
          set({ finishPreset: preset as FinishPreset });
        }
      },

      viewMode: 'split',
      setViewMode: (mode: string) => {
        if ((VALID_VIEW_MODES as readonly string[]).includes(mode)) {
          set({ viewMode: mode as ViewMode });
        }
      },

      // ── SSE Live Updates ────────────────────────────────────────────────
      sseConnected: false,
      connectSSE: (projectId: number) => {
        // Tear down any existing connection WITHOUT resetting the backoff
        // counter — we want exponential backoff across consecutive failures.
        cleanupEventSource(false);

        const url = `/api/v1/projects/${projectId}/live`;
        eventSource = new EventSource(url, { withCredentials: true });

        eventSource.addEventListener('connected', () => {
          console.log(`[SSE] Connected to project ${projectId} live updates`);
          reconnectAttempts = 0; // success → reset backoff
          set({ sseConnected: true });
        });

        eventSource.addEventListener('material_changed', (event) => {
          try {
            const data = JSON.parse(event.data);
            const { boq_item_id, total, rate, material_name } = data;

            const state = get();
            const updatedItems = state.boqItems.map((item) =>
              item.id === boq_item_id
                ? {
                    ...item,
                    total: total ?? item.total,
                    rate: rate ?? item.rate,
                    material_name: material_name ?? item.material_name,
                  }
                : item,
            );
            const newTotal = updatedItems.reduce(
              (sum, item) => sum + (item.total ?? 0),
              0,
            );
            set({ boqItems: updatedItems, projectTotal: newTotal });
          } catch (err) {
            console.error(
              '[SSE] Failed to parse material_changed event:',
              err,
            );
          }
        });

        eventSource.onerror = () => {
          console.warn('[SSE] Connection error, reconnecting…');
          set({ sseConnected: false });
          if (eventSource) {
            eventSource.close();
            eventSource = null;
          }

          const delay = getReconnectDelay();
          reconnectTimeoutId = setTimeout(() => {
            const { currentProjectId } = get();
            if (currentProjectId !== null) {
              get().connectSSE(currentProjectId);
            }
          }, delay);
        };
      },

      disconnectSSE: () => {
        // Full teardown — also resets the backoff counter because this is
        // an explicit user- or lifecycle-driven disconnect (e.g. project
        // switch, unmount).
        cleanupEventSource(true);
      },

      // ── Loading / error ────────────────────────────────────────────────
      loading: false,
      error: null,
    }),
    { name: 'project-store' },
  ),
);
