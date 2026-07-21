export interface Drawing {
  id: number;
  name: string;
  file_path: string;
  width_mm: number;
  height_mm: number;
  created_at: string;
  status: string;
}

export interface DetectedObject {
  id: number;
  drawing_id: number;
  object_type: string;
  label?: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation?: number;
  layer: string;
  properties?: Record<string, unknown>;
  boq_item_id?: number;
  // 3D viewer extended fields (optional — for scene objects)
  type?: 'wall' | 'partition' | 'door' | 'window' | 'furniture' | 'room' | 'other';
  position?: { x: number; y: number; z: number };
  dimensions?: { length: number; height: number; thickness: number };
  rotation3d?: { x: number; y: number; z: number };
}

export interface Material {
  id: number;
  name: string;
  brand: string;
  sku: string;
  rate: number;
  unit: string;
  lead_time_days: number;
  warranty: string;
  category: string;
}

export interface BOQItem {
  id: number;
  drawing_id: number;
  detected_object_id: number;
  description: string;
  quantity: number;
  unit: string;
  selected_material_id?: number;
}

export interface DrawingViewer2DProps {
  drawingId: number;
  objects: DetectedObject[];
  onObjectSelect?: (obj: DetectedObject) => void;
  selectedObjectId?: number | null;
  width?: number;
  height?: number;
}

export interface MaterialSelectorPanelProps {
  object: DetectedObject;
  boqItemId: number;
  onClose: () => void;
  onMaterialSelected: (materialId: number) => void;
}

export type FinishPreset = 'modern' | 'industrial' | 'luxury' | 'minimal';

export interface FinishPresetColors {
  wallColor: string;
  floorColor: string;
  accentColor: string;
  metalness: number;
  roughness: number;
}

export const FINISH_PRESETS: Record<FinishPreset, FinishPresetColors> = {
  modern: {
    wallColor: '#f0f0f0',
    floorColor: '#d4d4d4',
    accentColor: '#228be6',
    metalness: 0.3,
    roughness: 0.6,
  },
  industrial: {
    wallColor: '#8B8B8B',
    floorColor: '#585858',
    accentColor: '#e64949',
    metalness: 0.8,
    roughness: 0.4,
  },
  luxury: {
    wallColor: '#f5f0e8',
    floorColor: '#8B7355',
    accentColor: '#d4af37',
    metalness: 0.6,
    roughness: 0.2,
  },
  minimal: {
    wallColor: '#ffffff',
    floorColor: '#e0e0e0',
    accentColor: '#000000',
    metalness: 0.1,
    roughness: 0.8,
  },
};
