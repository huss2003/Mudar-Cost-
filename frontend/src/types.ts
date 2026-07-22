/**
 * Domain types — must mirror backend/app/schemas/* Pydantic models.
 */

// ─── Drawings ────────────────────────────────────────────────────────────

export interface Drawing {
  id: number;
  name: string;
  file_path: string;
  width_mm: number;
  height_mm: number;
  created_at: string;
  status: 'uploaded' | 'pending' | 'processing' | 'processed' | 'detected' | 'error';
  project_id?: number;
}

export interface DrawingUploadResponse {
  drawing_id: number;
  project_id: number;
  file_path: string;
  status: 'uploaded' | 'pending' | 'processing' | 'processed' | 'detected' | 'error';
  task_id: string | null;
  task_routing_hint: string | null;
}

export interface DrawingStatusResponse {
  drawing_id: number;
  status: Drawing['status'];
  objects_detected: number;
  error_message?: string | null;
}

export interface DetectedObject {
  id: number;
  drawing_id: number;
  object_type: string;
  label?: string | null;
  /** Location (mm) — rect origin */
  bbox_x: number;
  bbox_y: number;
  /** Size (mm) */
  length: number;
  width: number;
  height?: number | null;
  area?: number | null;
  thickness?: number | null;
  location_x?: number | null;
  location_y?: number | null;
  layer?: string | null;
  confidence?: number | null;
  /** Bounding-box [x, y, w, h] in mm */
  bbox_coords?: number[] | null;
  detection_source: 'rule' | 'ai' | 'hybrid';
  boq_item_id?: number | null;
}

// ─── Materials ───────────────────────────────────────────────────────────

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
  thumbnail_url?: string | null;
}

export interface Material extends MaterialOption {
  id: number;
  category: string;
}

// ─── BOQ ─────────────────────────────────────────────────────────────────

export interface BOQLineItem {
  id: number;
  detected_object_id?: number | null;
  description: string;
  quantity: number;
  unit: string;
  rate: number;
  total: number;
  trade: string | null;
  material_id?: number | null;
  material_name?: string | null;
  ruleset_version?: string | null;
  location?: string | null;
}

export interface BOQResponse {
  project_id: number;
  cost_version_id: number;
  total: number;
  trades: BOQLineItem[];
  summary: { trade: string; total: number; count: number }[];
  generated_at: string;
}

export interface BOQSummaryResponse {
  total: number;
  trades: { trade: string; total: number; count: number }[];
}

// ─── Projects ────────────────────────────────────────────────────────────

export type ProjectStatus = 'draft' | 'in_progress' | 'priced' | 'sent' | 'archived';
export const STATUS_LABELS: Record<ProjectStatus, string> = {
  draft: 'Draft',
  in_progress: 'In progress',
  priced: 'Priced',
  sent: 'Sent',
  archived: 'Archived',
};
export const STATUS_DOT: Record<ProjectStatus, string> = {
  draft: 'dot',
  in_progress: 'dot dot-pending',
  priced: 'dot dot-active',
  sent: 'dot dot-active',
  archived: 'dot',
};

export interface Project {
  id: number;
  name: string;
  client?: string | null;
  location?: string | null;
  created_at: string;
  updated_at: string;
  status: ProjectStatus;
  total?: number | null;
  drawings_count: number;
}

// ─── Cost engine ─────────────────────────────────────────────────────────

export interface CostVersionSummary {
  id: number;
  version_label: string;
  created_at: string;
  total: number;
  ruleset_version: string;
}

export interface TradeCostGroup {
  trade: string;
  total: number;
  count: number;
}

// ─── AI ──────────────────────────────────────────────────────────────────

export interface AskResponse {
  answer: string;
  citations: { trade?: string; line_id?: number; quote: string }[];
}

export interface MissingBOQResponse {
  missing: { trade: string; reason: string; suggested_qty: number; unit: string }[];
}

export interface AnomalyResponse {
  anomalies: { trade: string; line: string; expected: number; got: number; severity: 'low' | 'med' | 'high' }[];
}

export interface VEResponse {
  suggestions: { line_id: number; trade: string; change: string; saving: number }[];
  total_saving: number;
}

// ─── Finish presets (3D) ────────────────────────────────────────────────

export type FinishPreset = 'modern' | 'industrial' | 'luxury' | 'minimal';
export const FINISH_PRESET_LIST: readonly FinishPreset[] = ['modern', 'industrial', 'luxury', 'minimal'];

export interface FinishPresetColors {
  wallColor: string;
  floorColor: string;
  accentColor: string;
  metalness: number;
  roughness: number;
}

export const FINISH_PRESETS: Record<FinishPreset, FinishPresetColors> = {
  modern:    { wallColor: '#EDEAE1', floorColor: '#D7D2C2', accentColor: '#1B4D7E', metalness: 0.1, roughness: 0.7 },
  industrial:{ wallColor: '#5A574E', floorColor: '#3D3B36', accentColor: '#B8501F', metalness: 0.7, roughness: 0.3 },
  luxury:    { wallColor: '#F5F0E8', floorColor: '#A88E5B', accentColor: '#B8501F', metalness: 0.5, roughness: 0.3 },
  minimal:   { wallColor: '#FAFAF7', floorColor: '#EDEAE1', accentColor: '#1A1815', metalness: 0.05, roughness: 0.9 },
};
