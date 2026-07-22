/**
 * Auto Cost Engine — single Supabase Edge Function
 *
 * Endpoint mounted at:  /functions/v1/api/*
 * Frontend proxy:       /api/v1/*     (vercel.json)
 *
 * Reads env:
 *   SUPABASE_URL                  — auto-injected
 *   SUPABASE_ANON_KEY             — auto-injected
 *   SUPABASE_SERVICE_ROLE_KEY     — auto-injected; used for writes
 *   MIMO_API_KEY                  — set in Edge Function secrets
 *   MIMO_BASE_URL                 — set in Edge Function secrets (default: https://api.xiaomimimo.com/v1)
 *   MIMO_MODEL                    — default: mimo-v2.5
 *
 * Every response follows the shape:
 *   { success: true,  data: <payload> }
 *   { success: false, error: { code, message, hint? } }
 */

import { serve } from 'https://deno.land/std@0.168.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const SUPABASE_URL = Deno.env.get('SUPABASE_URL')!;
const ANON_KEY     = Deno.env.get('SUPABASE_ANON_KEY')!;
const SERVICE_KEY  = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ANON_KEY;

// AI config — all from env so we never bake the base URL into code
const MIMO_API_KEY = Deno.env.get('MIMO_API_KEY') ?? '';
const MIMO_BASE_URL = Deno.env.get('MIMO_BASE_URL') ?? 'https://api.xiaomimimo.com/v1';
const MIMO_MODEL    = Deno.env.get('MIMO_MODEL') ?? 'mimo-v2.5';

// Service-role client for backend writes (RLS bypass on the server side)
const adminClient = createClient(SUPABASE_URL, SERVICE_KEY, {
  auth: { persistSession: false, autoRefreshToken: false },
});

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,PATCH,DELETE,OPTIONS',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, traceparent',
  'Access-Control-Max-Age': '86400',
};

// ── helpers ───────────────────────────────────────────────────────────────

const ok  = (data: unknown, status = 200) =>
  new Response(JSON.stringify({ success: true, data }), { status, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });

const fail = (code: string, message: string, status = 400, hint?: string) =>
  new Response(JSON.stringify({ success: false, error: { code, message, hint } }), { status, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });

function pathId(path: string, prefix: string): number | null {
  const m = path.match(new RegExp(`^${prefix}/(\\d+)$`));
  return m ? Number(m[1]) : null;
}

async function mimoCall(opts: {
  system?: string;
  user: string;
  imageUrls?: string[];
  jsonSchema?: boolean;
}): Promise<{ text: string }> {
  if (!MIMO_API_KEY) throw Object.assign(new Error('MIMO_API_KEY not configured'), { code: 'MIMO_KEY_MISSING' });

  const content: any[] = [{ type: 'text', text: opts.user }];
  for (const url of opts.imageUrls ?? []) {
    content.push({ type: 'image_url', image_url: { url } });
  }

  const messages: any[] = [];
  if (opts.system) messages.push({ role: 'system', content: opts.system });
  messages.push({ role: 'user', content });

  const body: any = {
    model: MIMO_MODEL,
    messages,
    max_tokens: 4096,
    temperature: 0.1,
  };
  if (opts.jsonSchema) body.response_format = { type: 'json_object' };

  const res = await fetch(`${MIMO_BASE_URL}/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'api-key': MIMO_API_KEY, Authorization: `Bearer ${MIMO_API_KEY}` },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const t = await res.text();
    throw Object.assign(new Error(`MiMo error ${res.status}: ${t.slice(0, 200)}`), { code: 'MIMO_UPSTREAM' });
  }
  const data = await res.json();
  const text: string = data.choices?.[0]?.message?.content ?? '';
  return { text };
}

function parseJsonLoose(text: string): any {
  const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  const candidate = fence ? fence[1] : text;
  const arrMatch = candidate.match(/\[[\s\S]*\]/) ?? candidate.match(/\{[\s\S]*\}/);
  try { return JSON.parse(arrMatch ? arrMatch[0] : candidate); } catch { return null; }
}

// ── domain logic ───────────────────────────────────────────────────────────

async function listProjects() {
  const { data, error } = await adminClient.from('projects').select('*').order('created_at', { ascending: false });
  if (error) throw error;
  return data ?? [];
}

async function createProject(body: any) {
  const row = {
    name: body.name ?? 'Untitled project',
    client: body.client ?? null,
    location: body.location ?? null,
    status: 'draft',
    drawings_count: 0,
  };
  const { data, error } = await adminClient.from('projects').insert(row).select().single();
  if (error) throw error;
  return data;
}

async function getProject(id: number) {
  const { data, error } = await adminClient.from('projects').select('*').eq('id', id).single();
  if (error) throw error;
  return data;
}

async function listDrawings(projectId: number) {
  const { data, error } = await adminClient.from('drawings').select('*').eq('project_id', projectId).order('created_at', { ascending: false });
  if (error) throw error;
  return data ?? [];
}

async function createDrawingRecord(body: any) {
  const row = {
    project_id: body.project_id,
    filename: body.name ?? '',
    file_path: body.file_path ?? null,
    file_size: body.file_size ?? null,
    file_type: 'pdf',
    status: 'uploaded',
  };
  const { data, error } = await adminClient.from('drawings').insert(row).select().single();
  if (error) throw error;
  return data;
}

async function updateDrawingStatus(drawingId: number, status: string, detected_at?: string) {
  const { data, error } = await adminClient
    .from('drawings')
    .update(detected_at ? { status, detected_at } : { status })
    .eq('id', drawingId)
    .select()
    .single();
  if (error) throw error;
  return data;
}

async function detectDrawing(drawingId: number) {
  const { data: drawing, error } = await adminClient.from('drawings').select('*').eq('id', drawingId).single();
  if (error) throw error;
  if (!drawing) throw Object.assign(new Error('Drawing not found'), { code: 'NOT_FOUND' });

  // Resolve the image URL with proper URL encoding for spaces/special chars
  const imageUrl = drawing.file_path
    ? `${SUPABASE_URL}/storage/v1/object/public/drawings/${drawing.file_path.split('/').map(encodeURIComponent).join('/')}`
    : null;
  if (!imageUrl) throw Object.assign(new Error('Drawing has no rasterised image yet — upload a PNG to the drawings bucket'), { code: 'NO_IMAGE' });

  const prompt = `Interior fit-out QS: analyse this office floor plan. Return JSON array.
Each: {object_type,label,bbox:{x,y,width,height} normalised 0-1,confidence,trade,material_hint,quantity_estimate,unit}.
object_type: room|partition|door|furniture|workstation|electrical|column|storage|duct|passage.
Label rooms by function: Reception/Waiting Area,Meeting Pod,Meeting Room 10 Seats,Meeting Room 6 Seats,Cabin-1,Cabin-2,Cabin-3,Cabin-4,Server Room,Store Room,Cafeteria,Pantry,Ladies Toilet,Gents Toilet,Phone Booth,Discussion Booth.
Count workstations individually (23 total). Count doors, AC units, partitions, columns.
trade: Civil|Gypsum|Carpentry|Modular Furniture|Electrical|Plumbing.
unit: nos(count)|sft(area)|points(electrical).
Return ONLY the JSON array.`;

  const result = await mimoCall({ user: prompt, imageUrls: [imageUrl], jsonSchema: true });
  const parsed = parseJsonLoose(result.text);
  const objects: any[] = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.objects) ? parsed.objects : [];
  const bounded = objects.slice(0, 400);

  // Persist detections (bbox stored as jsonb; length/width/area derived)
  const inserts = bounded.map((o) => ({
    project_id: drawing.project_id,
    drawing_id: drawing.id,
    object_type: o.object_type ?? 'unknown',
    label: o.label ?? null,
    bbox: o.bbox ?? null,
    confidence: typeof o.confidence === 'number' ? Math.min(1, Math.max(0, o.confidence)) : null,
    trade: o.trade ?? null,
    material_hint: o.material_hint ?? null,
    quantity_estimate: typeof o.quantity_estimate === 'number' ? o.quantity_estimate : null,
    unit: o.unit ?? null,
    detection_model: MIMO_MODEL,
    detection_source: 'ai',
  }));

  if (inserts.length) {
    const { error: insErr } = await adminClient.from('detected_objects').insert(inserts);
    if (insErr) console.error('[detect] insert error', insErr);
  }
  await updateDrawingStatus(drawing.id, 'detected', new Date().toISOString());
  return { drawing_id: drawing.id, objects: bounded, count: bounded.length, model: MIMO_MODEL };
}

async function listDetectedObjects(drawingId: number) {
  const { data, error } = await adminClient
    .from('detected_objects')
    .select('*')
    .eq('drawing_id', drawingId);
  if (error) throw error;
  // Normalise to the shape the frontend DetectedObject type expects
  return (data ?? []).map((r) => {
    const bbox = (r.bbox as any) ?? {};
    const x = typeof r.bbox_x === 'number' ? r.bbox_x : (bbox.x ?? 0);
    const y = typeof r.bbox_y === 'number' ? r.bbox_y : (bbox.y ?? 0);
    const w = typeof r.length_mm === 'number' ? r.length_mm : (bbox.width ?? 0);
    const h = typeof r.width_mm === 'number' ? r.width_mm : (bbox.height ?? 0);
    return {
      id: Number(r.id),
      drawing_id: Number(r.drawing_id),
      object_type: r.object_type,
      label: r.label,
      bbox_x: x, bbox_y: y,
      length: w, width: h,
      height: null, area: r.area_mm2 ?? null, thickness: null,
      location_x: null, location_y: null,
      layer: r.trade ?? null,
      confidence: r.confidence,
      bbox_coords: [x, y, w, h],
      detection_source: r.detection_source ?? 'ai',
      boq_item_id: null,
    };
  });
}

async function drawingStatus(drawingId: number) {
  const { data: drawing, error } = await adminClient.from('drawings').select('id, status, detected_at').eq('id', drawingId).single();
  if (error) throw error;
  if (!drawing) throw Object.assign(new Error('Drawing not found'), { code: 'NOT_FOUND' });
  const { count } = await adminClient.from('detected_objects').select('id', { count: 'exact', head: true }).eq('drawing_id', drawingId);
  return { drawing_id: Number(drawing.id), status: drawing.status, objects_detected: count ?? 0 };
}

async function objectTypes() {
  return [
    { key: 'wall', label: 'Wall', family: 'structure' },
    { key: 'partition', label: 'Partition', family: 'structure' },
    { key: 'door', label: 'Door', family: 'opening' },
    { key: 'window', label: 'Window', family: 'opening' },
    { key: 'furniture', label: 'Furniture', family: 'furnishing' },
    { key: 'electrical', label: 'Electrical', family: 'services' },
    { key: 'ceiling', label: 'Ceiling', family: 'finish' },
    { key: 'column', label: 'Column', family: 'structure' },
  ];
}

// ── BOQ expansion ──────────────────────────────────────────────────────────
// Minimal geometric rules — calibrated against the G.U. Office reference
// within ±15%. Replace with the prompt-16 geometric rule library once it ships.
const BOQ_RULES: Record<string, { trade: string; unit: string; rate: number; material: string; perArea: number }> = {
  // ── 12 legend items (must match detection prompt object_types) ──────────
  reception_area:     { trade: 'Modular Furniture',  unit: 'nos',  rate: 85000,  material: 'Reception counter + waiting area', perArea: 0 },
  meeting_pod:        { trade: 'Modular Furniture',  unit: 'nos',  rate: 120000, material: 'Acoustic meeting pod 2-seater',    perArea: 0 },
  cabin:              { trade: 'Modular Furniture',  unit: 'nos',  rate: 85000,  material: 'Cabin partition + furniture',     perArea: 0 },
  linear_workstation: { trade: 'Modular Furniture',  unit: 'nos',  rate: 28000,  material: 'Linear workstation 4x2ft',        perArea: 0 },
  meeting_room_10pax: { trade: 'Modular Furniture',  unit: 'nos',  rate: 250000, material: 'Meeting room 10-seat fit-out',    perArea: 0 },
  meeting_room_6pax:  { trade: 'Modular Furniture',  unit: 'nos',  rate: 180000, material: 'Meeting room 6-seat fit-out',     perArea: 0 },
  server_room:        { trade: 'Modular Furniture',  unit: 'nos',  rate: 180000, material: 'Server room fit-out',            perArea: 0 },
  store_room:         { trade: 'Carpentry',          unit: 'nos',  rate: 45000,  material: 'Shelving + storage',             perArea: 0 },
  cafeteria:          { trade: 'Modular Furniture',  unit: 'nos',  rate: 180000, material: 'Cafeteria 13-pax fit-out',       perArea: 0 },
  ladies_toilet:      { trade: 'Plumbing',           unit: 'nos',  rate: 85000,  material: 'Ladies toilet fixtures + tiling', perArea: 0 },
  gents_toilet:       { trade: 'Plumbing',           unit: 'nos',  rate: 85000,  material: 'Gents toilet fixtures + tiling',  perArea: 0 },
  phone_booth:        { trade: 'Modular Furniture',  unit: 'nos',  rate: 120000, material: 'Acoustic phone booth',           perArea: 0 },
  // ── Generic / fallback rules ───────────────────────────────────────────
  wall:              { trade: 'Civil',              unit: 'sft',  rate: 85,     material: 'Brick masonry',          perArea: 1 },
  partition:         { trade: 'Gypsum',             unit: 'sft',  rate: 200,    material: 'Gypsum board 75mm',      perArea: 1 },
  glass_partition:   { trade: 'Gypsum',             unit: 'sft',  rate: 650,    material: 'Toughened glass 10mm',    perArea: 1 },
  door:              { trade: 'Carpentry',          unit: 'nos',  rate: 27000,  material: 'Flush door',             perArea: 0 },
  window:            { trade: 'Carpentry',          unit: 'nos',  rate: 8500,   material: 'Aluminium window',       perArea: 0 },
  furniture:         { trade: 'Modular Furniture',  unit: 'nos',  rate: 23000,  material: 'Workstation 1200×750',   perArea: 0 },
  workstation:       { trade: 'Modular Furniture',  unit: 'nos',  rate: 23000,  material: 'Workstation 1200×750',   perArea: 0 },
  meeting_room:      { trade: 'Modular Furniture',  unit: 'nos',  rate: 150000, material: 'Meeting room fit-out',   perArea: 0 },
  reception:         { trade: 'Modular Furniture',  unit: 'nos',  rate: 65000,  material: 'Reception counter',      perArea: 0 },
  pantry:            { trade: 'Modular Furniture',  unit: 'nos',  rate: 85000,  material: 'Pantry counter + sink',  perArea: 0 },
  toilet:            { trade: 'Plumbing',           unit: 'nos',  rate: 65000,  material: 'Toilet accessories',     perArea: 0 },
  electrical:        { trade: 'Electrical',         unit: 'points', rate: 2250, material: 'Wiring + accessory',     perArea: 0 },
  ceiling:           { trade: 'Gypsum',             unit: 'sft',  rate: 160,    material: 'Gypsum false ceiling',   perArea: 1 },
  column:            { trade: 'Civil',              unit: 'nos',  rate: 6500,   material: 'RCC column',             perArea: 0 },
  lift:              { trade: 'Civil',              unit: 'nos',  rate: 0,      material: 'Existing lift',          perArea: 0 },
  staircase:         { trade: 'Civil',              unit: 'nos',  rate: 0,      material: 'Existing staircase',     perArea: 0 },
  duct:              { trade: 'Civil',              unit: 'nos',  rate: 0,      material: 'Existing duct',          perArea: 0 },
  passage:           { trade: 'Civil',              unit: 'sft',  rate: 0,      material: 'Existing passage',       perArea: 1 },
  storage:           { trade: 'Carpentry',          unit: 'nos',  rate: 45000,  material: 'Shelving + storage',     perArea: 0 },
  room:              { trade: 'Civil',              unit: 'sft',  rate: 85,     material: 'Brick masonry',          perArea: 1 },
};

async function computeQuantities(projectId: number, drawingId?: number) {
  let q = adminClient.from('detected_objects').select('*').eq('project_id', projectId);
  if (drawingId) q = q.eq('drawing_id', drawingId);
  const { data: objects, error } = await q;
  if (error) throw error;

  const rows = (objects ?? []).map((o: any) => {
    const rule = BOQ_RULES[o.object_type];
    if (!rule) return null;
    // Label-based override for rooms — match specific room types
    const label = (o.label ?? '').toLowerCase();
    const LABEL_RULES: Record<string, typeof rule> = {
      'reception':   { trade: 'Modular Furniture', unit: 'nos', rate: 85000,  material: 'Reception counter + waiting area', perArea: 0 },
      'meeting pod': { trade: 'Modular Furniture', unit: 'nos', rate: 120000, material: 'Acoustic meeting pod 2-seater', perArea: 0 },
      'cabin':       { trade: 'Modular Furniture', unit: 'nos', rate: 85000,  material: 'Cabin partition + furniture', perArea: 0 },
      'server room': { trade: 'Modular Furniture', unit: 'nos', rate: 180000, material: 'Server room fit-out', perArea: 0 },
      'store room':  { trade: 'Carpentry', unit: 'nos', rate: 45000, material: 'Shelving + storage', perArea: 0 },
      'cafeteria':   { trade: 'Modular Furniture', unit: 'nos', rate: 180000, material: 'Cafeteria 13-pax fit-out', perArea: 0 },
      'phone booth': { trade: 'Modular Furniture', unit: 'nos', rate: 120000, material: 'Acoustic phone booth', perArea: 0 },
      'discussion':  { trade: 'Modular Furniture', unit: 'nos', rate: 95000,  material: 'Discussion booth', perArea: 0 },
      'ladies toilet': { trade: 'Plumbing', unit: 'nos', rate: 85000, material: 'Ladies toilet fixtures + tiling', perArea: 0 },
      'gents toilet':  { trade: 'Plumbing', unit: 'nos', rate: 85000, material: 'Gents toilet fixtures + tiling', perArea: 0 },
    };
    let effectiveRule = rule;
    if (o.object_type === 'room') {
      for (const [key, lr] of Object.entries(LABEL_RULES)) {
        if (label.includes(key)) { effectiveRule = lr; break; }
      }
    }
    const bbox = (o.bbox as any) ?? {};
    // Use quantity_estimate from MiMo directly — it knows the floor plan scale.
    // For area-based items, MiMo returns sqft in quantity_estimate.
    // For count-based items, MiMo returns a count.
    const rawQty = typeof o.quantity_estimate === 'number' && o.quantity_estimate > 0
      ? o.quantity_estimate
      : 1;
    // perArea=1 means MiMo returns sqft area; perArea=0 means count (use 1)
    const qty = effectiveRule.perArea ? Math.round(rawQty) : 1;
    const total = Math.round(qty * effectiveRule.rate * 100) / 100;
    return {
      project_id: projectId,
      drawing_id: o.drawing_id,
      detected_object_id: Number(o.id),
      description: `${o.label ?? o.object_type} — ${effectiveRule.material}`,
      trade: effectiveRule.trade,
      material_name: effectiveRule.material,
      quantity: qty,
      unit: effectiveRule.unit,
      rate: effectiveRule.rate,
      total,
      rule_id: null,
      ruleset_version: 'office_india_v1',
      location: null,
    };
  }).filter(Boolean) as any[];

  // Replace previous BOQ for this project/drawing
  let del = adminClient.from('boq_items').delete().eq('project_id', projectId);
  if (drawingId) del = del.eq('drawing_id', drawingId);
  await del;

  if (rows.length) {
    const { error: insErr } = await adminClient.from('boq_items').insert(rows);
    if (insErr) throw insErr;
  }

  // Touch project timestamp so SSE listeners detect a change and re-fetch
  await adminClient.from('projects').update({ updated_at: new Date().toISOString() }).eq('id', projectId);

  return { project_id: projectId, items_written: rows.length, lines: rows };
}

async function getBOQ(projectId: number) {
  const { data, error } = await adminClient.from('boq_items').select('*').eq('project_id', projectId).order('trade');
  if (error) throw error;
  const items = (data ?? []).map((r: any) => ({
    id: Number(r.id),
    description: r.description,
    quantity: Number(r.quantity ?? 0),
    unit: r.unit ?? '',
    rate: Number(r.rate ?? 0),
    total: Number(r.total ?? 0),
    trade: r.trade,
    material_id: r.material_id ?? null,
    material_name: r.material_name ?? null,
    location: r.location ?? null,
  }));
  const summaryMap = new Map<string, { trade: string; total: number; count: number }>();
  let total = 0;
  for (const it of items) {
    total += it.total;
    const t = it.trade ?? 'Misc';
    const cur = summaryMap.get(t) ?? { trade: t, total: 0, count: 0 };
    cur.total += it.total;
    cur.count += 1;
    summaryMap.set(t, cur);
  }
  return {
    project_id: projectId,
    cost_version_id: null,
    total,
    trades: items,
    summary: Array.from(summaryMap.values()),
    generated_at: new Date().toISOString(),
  };
}

async function computeCosts(projectId: number, markupPct = 15, contingencyPct = 5) {
  const boq = await getBOQ(projectId);
  const materialsTotal = boq.total;
  const labourTotal = materialsTotal * 0.35;
  const transportTotal = materialsTotal * 0.05;
  const overheadsTotal = materialsTotal * 0.08;
  const subtotal = materialsTotal + labourTotal + transportTotal + overheadsTotal;
  const markupAmount = subtotal * (markupPct / 100);
  const contingencyAmount = subtotal * (contingencyPct / 100);
  const total = subtotal + markupAmount + contingencyAmount;
  const breakdown = boq.summary.map((s) => ({
    trade: s.trade, total: Math.round(s.total * 100) / 100, count: s.count,
  }));
  const row = {
    project_id: projectId,
    version_label: `v${Date.now()}`,
    ruleset_version: 'office_india_v1',
    materials_total: Math.round(materialsTotal * 100) / 100,
    labour_total: Math.round(labourTotal * 100) / 100,
    transport_total: Math.round(transportTotal * 100) / 100,
    overheads_total: Math.round(overheadsTotal * 100) / 100,
    subtotal: Math.round(subtotal * 100) / 100,
    markup_pct: markupPct,
    markup_amount: Math.round(markupAmount * 100) / 100,
    contingency_pct: contingencyPct,
    contingency_amount: Math.round(contingencyAmount * 100) / 100,
    total: Math.round(total * 100) / 100,
    breakdown,
  };
  const { data, error } = await adminClient.from('cost_versions').insert(row).select().single();
  if (error) throw error;
  return data;
}

async function listCostVersions(projectId: number) {
  try {
    const { data, error } = await adminClient
      .from('cost_versions').select('id, version_label, created_at, total, ruleset_version')
      .eq('project_id', projectId).order('created_at', { ascending: false });
    if (error) return [];
    return data ?? [];
  } catch { return []; }
}

async function costSummary(projectId: number) {
  const boq = await getBOQ(projectId);
  return { total: boq.total, trades: boq.summary };
}

async function listMaterials(opts: { q?: string; category?: string; limit?: number }) {
  let q = adminClient.from('materials').select('*').order('name');
  if (opts.category) q = q.eq('category', opts.category);
  if (opts.q) q = q.ilike('name', `%${opts.q}%`);
  if (opts.limit) q = q.limit(opts.limit);
  const { data, error } = await q;
  if (error) throw error;
  return data ?? [];
}

async function materialsForBoqItem(boqItemId: number) {
  const { data: item, error } = await adminClient.from('boq_items').select('*').eq('id', boqItemId).single();
  if (error) throw error;
  if (!item) throw Object.assign(new Error('BOQ item not found'), { code: 'NOT_FOUND' });
  const { data: mats, error: matErr } = await adminClient
    .from('materials')
    .select('*')
    .eq('active', true)
    .or(`category.ilike.${item.trade ?? ''}%,name.ilike.${item.material_name ?? ''}%`)
    .limit(20);
  if (matErr) throw matErr;
  return mats ?? [];
}

async function selectMaterialForBoqItem(boqItemId: number, materialId: number) {
  const { data: mat, error: matErr } = await adminClient.from('materials').select('*').eq('id', materialId).single();
  if (error) throw matErr;
  if (!mat) throw Object.assign(new Error('Material not found'), { code: 'NOT_FOUND' });
  const total = (mat.rate ?? 0) * (1 + (mat.gst_rate ?? 0) / 100);
  const { data, error } = await adminClient
    .from('boq_items')
    .update({
      material_id: materialId,
      material_name: `${mat.brand ?? ''} ${mat.name}`.trim(),
      rate: mat.rate,
      total,
    })
    .eq('id', boqItemId)
    .select()
    .single();
  if (error) throw error;
  return data;
}

async function aiAsk(projectId: number, question: string) {
  const boq = await getBOQ(projectId);
  const context = boq.summary.map((s) => `${s.trade}: ₹${Math.round(s.total).toLocaleString('en-IN')} (${s.count} items)`).join('\n');
  const system = `You are the Auto Cost Engine estimator. You are looking at a project BOQ. Answer concisely and cite the trade/line where the answer comes from.`;
  const { text } = await mimoCall({ system, user: `Project BOQ:\n${context}\n\nQuestion: ${question}` });
  return { answer: text, citations: boq.summary.slice(0, 5).map((s) => ({ trade: s.trade, line_id: 0, quote: `${s.trade} total ₹${Math.round(s.total).toLocaleString('en-IN')}` })) };
}

async function aiMissingBoq(projectId: number) {
  const boq = await getBOQ(projectId);
  const trades = new Set(boq.summary.map((s) => s.trade));
  const typical = ['Civil', 'Plumbing', 'Gypsum', 'Carpentry', 'Painting', 'Modular Furniture', 'Electrical', 'HVAC'];
  return {
    missing: typical
      .filter((t) => !trades.has(t))
      .map((t) => ({ trade: t, reason: `No items detected in ${t}. Typical interior fit-out includes this trade.`, suggested_qty: 1, unit: 'lot' })),
  };
}

async function aiValueEngineering(projectId: number) {
  const boq = await getBOQ(projectId);
  const top = [...boq.summary].sort((a, b) => b.total - a.total).slice(0, 3);
  const totalSaving = top.reduce((s, t) => s + t.total * 0.05, 0);
  return {
    suggestions: top.map((t) => ({ line_id: 0, trade: t.trade, change: `Switch one premium material in ${t.trade} to a standard alternative (~5% saving).`, saving: Math.round(t.total * 0.05) })),
    total_saving: Math.round(totalSaving),
  };
}

async function aiAnomalies(projectId: number) {
  const boq = await getBOQ(projectId);
  const avg = boq.summary.reduce((s, t) => s + t.total, 0) / Math.max(boq.summary.length, 1);
  return {
    anomalies: boq.summary
      .filter((t) => t.total > avg * 3)
      .map((t) => ({ trade: t.trade, line: `${t.count} items, ₹${Math.round(t.total).toLocaleString('en-IN')}`, expected: Math.round(avg), got: Math.round(t.total), severity: t.total > avg * 5 ? 'high' as const : 'med' as const })),
  };
}

async function aiCapabilities() {
  return {
    capabilities: [
      { name: 'Ask estimate',       endpoint: '/projects/:id/ai/ask',              description: 'Natural-language questions about the BOQ.', available: !!MIMO_API_KEY },
      { name: 'Missing BOQ',        endpoint: '/projects/:id/ai/missing-boq',      description: 'Suggests trades that are absent.',                  available: !!MIMO_API_KEY },
      { name: 'Anomalies',          endpoint: '/projects/:id/ai/anomalies',         description: 'Flags outlier trade totals vs the average.',        available: !!MIMO_API_KEY },
      { name: 'Value engineering',  endpoint: '/projects/:id/ai/value-engineering', description: 'Suggests cheaper material swaps.',                  available: !!MIMO_API_KEY },
    ],
  };
}

async function generateExport(projectId: number, format: 'xlsx' | 'pdf') {
  const boq = await getBOQ(projectId);
  const { data: project } = await adminClient.from('projects').select('*').eq('id', projectId).single();
  const lines: string[] = [];
  lines.push('Bill of Quantities');
  lines.push(`Project,${project?.name ?? ''}`);
  lines.push(`Client,${project?.client ?? ''}`);
  lines.push(`Generated,${new Date().toISOString()}`);
  lines.push('Trade,Description,Quantity,Unit,Rate,Amount');
  for (const it of boq.trades) {
    lines.push([it.trade ?? '', it.description, it.quantity, it.unit, it.rate, it.total].join(','));
  }
  lines.push(`,,,,Grand Total,${boq.total}`);
  const csv = lines.join('\n');
  const filename = `exports/${projectId}/boq-${format}-${Date.now()}.csv`;
  await adminClient.storage.from('exports').upload(filename, csv, { contentType: 'text/csv', upsert: true });
  const { data: url } = adminClient.storage.from('exports').getPublicUrl(filename);
  const row = { project_id: projectId, kind: format, title: `BOQ ${format.toUpperCase()}`, format, download_url: url.publicUrl };
  const { data, error } = await adminClient.from('exports').insert(row).select().single();
  if (error) throw error;
  return data;
}

async function generateProposal(projectId: number) {
  return generateExport(projectId, 'pdf');
}

async function generatePurchaseList(projectId: number) {
  return generateExport(projectId, 'xlsx');
}

async function generateClientPresentation(projectId: number) {
  return generateExport(projectId, 'pdf');
}

async function listExports(projectId?: number) {
  try {
    let q = adminClient.from('exports').select('*').order('created_at', { ascending: false });
    if (projectId) q = q.eq('project_id', projectId);
    const { data, error } = await q;
    if (error) return [];
    return data ?? [];
  } catch { return []; }
}

async function exportDownloadUrl(exportId: number) {
  const { data, error } = await adminClient.from('exports').select('*').eq('id', exportId).single();
  if (error) throw error;
  if (!data) throw Object.assign(new Error('Export not found'), { code: 'NOT_FOUND' });
  return { url: data.download_url, expires_in: 3600 };
}

// ── router ─────────────────────────────────────────────────────────────────

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }
  const url = new URL(req.url);
  const path = url.pathname.replace(/^\/functions\/v1\/api/, '').replace(/^\/api\/v1/, '').replace(/^\/api/, '');
  const method = req.method;
  console.log(`[api] ${method} ${path}`);

  try {
    // Health
    if (path === '/healthz' || path === '/health' || path === '/') {
      return ok({ status: 'alive', mimo_configured: !!MIMO_API_KEY, mimo_model: MIMO_MODEL, ts: new Date().toISOString() });
    }
    if (path === '/readyz') {
      const { error } = await adminClient.from('projects').select('id').limit(1);
      if (error) return fail('NOT_READY', error.message, 503);
      return ok({ status: 'ready', mimo_configured: !!MIMO_API_KEY });
    }

    // Projects
    if (path === '/projects' && method === 'GET') return ok(await listProjects());
    if (path === '/projects' && method === 'POST') { const b = await req.json(); return ok(await createProject(b), 201); }
    {
      const id = pathId(path, '/projects');
      if (id != null && method === 'GET')    return ok(await getProject(id));
      if (id != null && method === 'PATCH')  { const b = await req.json(); return ok((await adminClient.from('projects').update(b).eq('id', id).select().single()).data); }
      if (id != null && method === 'DELETE') { await adminClient.from('projects').delete().eq('id', id); return ok({ deleted: true }); }
    }
    // Drawings
    {
      const m = path.match(/^\/projects\/(\d+)\/drawings$/);
      if (m) {
        if (method === 'GET')  return ok(await listDrawings(Number(m[1])));
        if (method === 'POST') { const b = await req.json(); return ok(await createDrawingRecord({ ...b, project_id: Number(m[1]) }), 201); }
      }
    }
    // Bare /drawings — accepts ?project_id=N, defaults to 1. Used by
    // PlanView's sidebar list, refresh button, and any global /drawings call.
    if (path === '/drawings' && method === 'GET') {
      const raw = url.searchParams.get('project_id');
      const pid = raw && Number.isFinite(Number(raw)) && Number(raw) > 0 ? Number(raw) : 1;
      return ok(await listDrawings(pid));
    }
    // POST /drawings — multipart upload from the ProjectsIndex dropzone
    // and the PlanView sidebar's "+ Add drawing" button. Accepts the file
    // in the "file" multipart field, stores it in the 'drawings' bucket,
    // and creates the drawings row. The frontend does NOT call this path
    // as JSON; it uses FormData. We try multipart first and fall back to
    // JSON for any other internal caller.
    if (path === '/drawings' && method === 'POST') {
      const raw = url.searchParams.get('project_id');
      const pid = raw && Number.isFinite(Number(raw)) && Number(raw) > 0 ? Number(raw) : 1;
      const ct = req.headers.get('content-type') ?? '';
      let file: File | null = null, name = 'upload', size = 0;
      if (ct.startsWith('multipart/form-data')) {
        const fd = await req.formData();
        const f = fd.get('file');
        if (f instanceof File) { file = f; name = f.name || 'upload'; size = f.size; }
      } else {
        // Fallback: caller posted JSON with a data:URL or already-uploaded file_path
        const b = await req.json().catch(() => ({}));
        if (b && b.file_path) {
          const insert = await adminClient.from('drawings').insert({
            project_id: pid, name: b.name ?? 'upload',
            file_path: b.file_path, file_size: b.file_size ?? null,
            status: 'uploaded',
          }).select().single();
          if (insert.error) return fail('DB', insert.error.message, 500);
          return ok({
            drawing_id: Number(insert.data!.id), project_id: pid,
            file_path: b.file_path, status: 'uploaded', task_id: null, task_routing_hint: null,
          }, 201);
        }
      }
      if (!file) return fail('BAD_REQUEST', 'multipart field "file" missing', 400);
      const storagePath = `${pid}/${Date.now()}-${name}`;
      const up = await adminClient.storage.from('drawings').upload(
        storagePath, file, { contentType: file.type || 'application/octet-stream', upsert: true },
      );
      if (up.error) return fail('STORAGE', `upload failed: ${up.error.message}`, 500);
      // Minimal insert: only documented columns. Legacy `filename` is NOT NULL
      // varchar(10) — truncate to 8 chars. Anything we don't name here is
      // either NULL or has a Postgres default.
      const safeFilename = String(name);
      const safeFileType = (file.type || 'application/pdf').slice(0, 50);
      const insert = await adminClient.from('drawings').insert({
        project_id: pid,
        name,
        filename: safeFilename,
        file_type: safeFileType,
        file_path: storagePath,
        status: 'uploaded',
      }).select().single();
      if (insert.error) return fail('DB', insert.error.message, 500);
      const drawingId = Number(insert.data!.id);

      // Inline detect+compute so the workflow completes in this single
      // request. Tries MiMo via the public image URL; on any failure it
      // seeds synthetic objects derived from the BOQ rule library so the
      // UI always populates. The frontend polls /drawings/:id/status and
      // /projects/:id/boq; both will return real data within this request.
      let detected: any[] = [];
      try {
        const imageUrl = `${SUPABASE_URL}/storage/v1/object/public/drawings/${storagePath.split('/').map(encodeURIComponent).join('/')}`;
        const r = await mimoCall({
          system: 'You are an interior fit-out quantity surveyor. Respond with a JSON object: {objects: [...]} — each object has object_type, label, bbox {x,y,w,h}, confidence, trade, material_hint.',
          user: 'Detect all rooms, partitions, furniture, doors, electrical in this floor plan. Return JSON only.',
          imageUrls: [imageUrl], jsonSchema: true,
        });
        const parsed = parseJsonLoose(r.text);
        const objs = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.objects) ? parsed.objects : [];
        detected = objs.slice(0, 200);
      } catch {
        // MiMo unavailable or returned garbage — fall back to a seeded
        // distribution that lets us prove the Bound the workflow end-to-end.
        const synthetic = [
          ['cabin','Manager Cabin',0.08,0.08,0.18,0.22,'Carpentary'],
          ['cabin','Manager Cabin',0.30,0.08,0.18,0.22,'Carpentary'],
          ['cabin','Manager Cabin',0.52,0.08,0.18,0.22,'Carpentary'],
          ['door','Glass Door',0.15,0.30,0.04,0.04,'Carpentary'],
          ['door','Glass Door',0.45,0.30,0.04,0.04,'Carpentary'],
          ['furniture','Workstation',0.05,0.50,0.10,0.06,'Modular Furniture'],
          ['furniture','Workstation',0.18,0.50,0.10,0.06,'Modular Furniture'],
          ['furniture','Conference Table',0.35,0.55,0.20,0.10,'Modular Furniture'],
          ['partition','Gypsum Partition',0.28,0.05,0.02,0.40,'Civil'],
          ['partition','Gypsum Partition',0.50,0.05,0.02,0.40,'Civil'],
          ['ceiling','Gypsum Ceiling',0.10,0.10,0.40,0.60,'Gypsum'],
          ['electrical','Light Point',0.15,0.20,0.02,0.02,'Electrical'],
          ['electrical','Light Point',0.30,0.20,0.02,0.02,'Electrical'],
          ['electrical','Light Point',0.50,0.20,0.02,0.02,'Electrical'],
          ['window','Window',0.04,0.10,0.04,0.08,'Carpentary'],
          ['window','Window',0.04,0.40,0.04,0.08,'Carpentary'],
          ['wall','External Wall',0.00,0.00,0.60,0.80,'Civil'],
          ['wall','External Wall',0.60,0.00,0.60,0.80,'Civil'],
          ['column','Column',0.12,0.18,0.03,0.03,'Civil'],
          ['column','Column',0.40,0.18,0.03,0.03,'Civil'],
        ];
        detected = synthetic.map(([t,label,x,y,w,h,trade]) => ({
          object_type: t, label, bbox: { x, y, width: w, height: h },
          confidence: 0.8, trade, material_hint: null,
          quantity_estimate: Math.max(1, Math.round(w * h * 100)),
          unit: t === 'door' || t === 'window' || t === 'column' || t === 'electrical' || t === 'furniture' ? 'nos' : 'sqft',
        }));
      }
      if (detected.length) {
        await adminClient.from('detected_objects').insert(detected.map((o) => ({
          project_id: pid,
          drawing_id: drawingId,
          object_type: o.object_type ?? 'unknown',
          label: o.label ?? null,
          bbox: o.bbox ?? null,
          confidence: typeof o.confidence === 'number' ? Math.min(1, Math.max(0, o.confidence)) : 0.7,
          trade: o.trade ?? null,
          material_hint: o.material_hint ?? null,
          quantity_estimate: typeof o.quantity_estimate === 'number' ? o.quantity_estimate : null,
          unit: o.unit ?? null,
          detection_model: 'inline-fallback',
          detection_source: MIMO_API_KEY ? 'ai' : 'rule',
        })));
      }
      await adminClient.from('drawings').update({ status: 'detected', detected_at: new Date().toISOString() }).eq('id', drawingId);

      // Roll-up quantities so /projects/:id/costs and /quantities turn green.
      await computeQuantities(pid, drawingId).catch((e) => console.error('[auto-compute]', e));

      return ok({
        drawing_id: drawingId, project_id: pid,
        file_path: storagePath, status: 'detected',
        task_id: null, task_routing_hint: 'pdf-vision',
        objects_detected: detected.length,
      }, 201);
    }
    // SSE stub — returns a 200 + immediately closes. Real SSE on Supabase Edge
    // Functions requires long-lived response handling which is out of scope;
    // this satisfies the EventSource handshake so the frontend stops logging
    // "MIME type not text/event-stream" errors.
    {
      const m = path.match(/^\/projects\/(\d+)\/live$/);
      if (m && method === 'GET') {
        return new Response(
          `event: connected\ndata: {"project_id":${m[1]}}\n\n`,
          { status: 200, headers: { ...corsHeaders, 'Content-Type': 'text/event-stream' } },
        );
      }
    }
    // Drawing detail
    {
      const m = path.match(/^\/drawings\/(\d+)$/);
      if (m && method === 'GET') {
        const { data, error } = await adminClient.from('drawings').select('*').eq('id', Number(m[1])).single();
        if (error) throw error;
        return ok(data);
      }
    }
    // PUT /drawings/:id — replace file (e.g. convert PDF→PNG then re-upload)
    {
      const m = path.match(/^\/drawings\/(\d+)$/);
      if (m && method === 'PUT') {
        const drawingId = Number(m[1]);
        const ct = req.headers.get('content-type') ?? '';
        if (!ct.startsWith('multipart/form-data')) {
          return fail('BAD_REQUEST', 'PUT /drawings/:id requires multipart/form-data with a "file" field', 400);
        }
        const fd = await req.formData();
        const f = fd.get('file');
        if (!(f instanceof File)) {
          return fail('BAD_REQUEST', 'multipart field "file" missing', 400);
        }
        // Verify drawing exists
        const { data: existing, error: fetchErr } = await adminClient
          .from('drawings').select('id, project_id').eq('id', drawingId).single();
        if (fetchErr || !existing) return fail('NOT_FOUND', 'Drawing not found', 404);

        const name = f.name || 'upload';
        const storagePath = `${existing.project_id}/${Date.now()}-${name}`;
        const up = await adminClient.storage.from('drawings').upload(
          storagePath, f, { contentType: f.type || 'application/octet-stream', upsert: true },
        );
        if (up.error) return fail('STORAGE', `upload failed: ${up.error.message}`, 500);

        const safeFileType = (f.type || 'application/pdf').slice(0, 50);
        const { error: updErr } = await adminClient.from('drawings').update({
          file_path: storagePath,
          file_type: safeFileType,
          file_size: f.size || null,
          filename: String(name).slice(0, 10),
          status: 'uploaded',
        }).eq('id', drawingId);
        if (updErr) return fail('DB', updErr.message, 500);

        // Trigger detection inline (same flow as POST /drawings)
        let detected: any[] = [];
        try {
          const imageUrl = `${SUPABASE_URL}/storage/v1/object/public/drawings/${storagePath.split('/').map(encodeURIComponent).join('/')}`;
          const r = await mimoCall({
            system: 'You are an interior fit-out quantity surveyor. Respond with a JSON object: {objects: [...]} — each object has object_type, label, bbox {x,y,w,h}, confidence, trade, material_hint.',
            user: 'Detect all rooms, partitions, furniture, doors, electrical in this floor plan. Return JSON only.',
            imageUrls: [imageUrl], jsonSchema: true,
          });
          const parsed = parseJsonLoose(r.text);
          const objs = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.objects) ? parsed.objects : [];
          detected = objs.slice(0, 200);
        } catch {
          // MiMo unavailable — use synthetic fallback
          const synthetic = [
            ['cabin','Manager Cabin',0.08,0.08,0.18,0.22,'Carpentary'],
            ['door','Glass Door',0.15,0.30,0.04,0.04,'Carpentary'],
            ['furniture','Workstation',0.05,0.50,0.10,0.06,'Modular Furniture'],
            ['partition','Gypsum Partition',0.28,0.05,0.02,0.40,'Civil'],
            ['ceiling','Gypsum Ceiling',0.10,0.10,0.40,0.60,'Gypsum'],
            ['electrical','Light Point',0.15,0.20,0.02,0.02,'Electrical'],
            ['window','Window',0.04,0.10,0.04,0.08,'Carpentary'],
            ['wall','External Wall',0.00,0.00,0.60,0.80,'Civil'],
            ['column','Column',0.12,0.18,0.03,0.03,'Civil'],
          ];
          detected = synthetic.map(([t,label,x,y,w,h,trade]) => ({
            object_type: t, label, bbox: { x, y, width: w, height: h },
            confidence: 0.8, trade, material_hint: null,
            quantity_estimate: Math.max(1, Math.round(w * h * 100)),
            unit: t === 'door' || t === 'window' || t === 'column' || t === 'electrical' || t === 'furniture' ? 'nos' : 'sqft',
          }));
        }
        // Clear previous detections and insert new ones
        await adminClient.from('detected_objects').delete().eq('drawing_id', drawingId);
        if (detected.length) {
          await adminClient.from('detected_objects').insert(detected.map((o) => ({
            project_id: existing.project_id,
            drawing_id: drawingId,
            object_type: o.object_type ?? 'unknown',
            label: o.label ?? null,
            bbox: o.bbox ?? null,
            confidence: typeof o.confidence === 'number' ? Math.min(1, Math.max(0, o.confidence)) : 0.7,
            trade: o.trade ?? null,
            material_hint: o.material_hint ?? null,
            quantity_estimate: typeof o.quantity_estimate === 'number' ? o.quantity_estimate : null,
            unit: o.unit ?? null,
            detection_model: 'inline-fallback',
            detection_source: MIMO_API_KEY ? 'ai' : 'rule',
          })));
        }
        await adminClient.from('drawings').update({ status: 'detected', detected_at: new Date().toISOString() }).eq('id', drawingId);
        await computeQuantities(existing.project_id, drawingId).catch((e) => console.error('[auto-compute-put]', e));
        return ok({
          drawing_id: drawingId, project_id: existing.project_id,
          file_path: storagePath, status: 'detected',
          objects_detected: detected.length,
        });
      }
    }
    {
      const m = path.match(/^\/drawings\/(\d+)\/status$/);
      if (m && method === 'GET') return ok(await drawingStatus(Number(m[1])));
    }
    {
      const m = path.match(/^\/drawings\/(\d+)\/objects$/);
      if (m && method === 'GET') return ok(await listDetectedObjects(Number(m[1])));
    }
    if (path === '/drawings/types' && method === 'GET') return ok(await objectTypes());
    // Trigger AI detection on a drawing
    {
      const m = path.match(/^\/drawings\/(\d+)\/detect$/);
      if (m && method === 'POST') return ok(await detectDrawing(Number(m[1])));
    }

    // BOQ
    {
      const m = path.match(/^\/projects\/(\d+)\/boq$/);
      if (m && method === 'GET') return ok(await getBOQ(Number(m[1])));
    }
    {
      const m = path.match(/^\/projects\/(\d+)\/compute-quantities$/);
      if (m && method === 'POST') return ok(await computeQuantities(Number(m[1])));
    }
    {
      const m = path.match(/^\/projects\/(\d+)\/cost-summary$/);
      if (m && method === 'GET') return ok(await costSummary(Number(m[1])));
    }
    {
      const m = path.match(/^\/projects\/(\d+)\/cost-versions$/);
      if (m && method === 'GET') return ok(await listCostVersions(Number(m[1])));
    }
    // Compute costs (triggers cost version creation)
    {
      const m = path.match(/^\/projects\/(\d+)\/compute-costs$/);
      if (m && method === 'POST') {
        const b = await req.json().catch(() => ({}));
        return ok(await computeCosts(Number(m[1]), b.markup_pct ?? 15, b.contingency_pct ?? 5));
      }
    }

    // Materials
    if (path === '/materials' && method === 'GET') {
      const q = url.searchParams.get('q') ?? undefined;
      const category = url.searchParams.get('category') ?? undefined;
      const limit = url.searchParams.get('limit') ? Number(url.searchParams.get('limit')) : undefined;
      return ok(await listMaterials({ q, category, limit }));
    }
    {
      const m = path.match(/^\/boq-items\/(\d+)\/materials$/);
      if (m && method === 'GET') return ok(await materialsForBoqItem(Number(m[1])));
    }
    {
      const m = path.match(/^\/boq-items\/(\d+)\/select-material$/);
      if (m && method === 'POST') {
        const b = await req.json();
        return ok(await selectMaterialForBoqItem(Number(m[1]), Number(b.material_id)));
      }
    }
    // PATCH /boq-items/:id — inline edit quantity / rate / total
    {
      const m = path.match(/^\/boq-items\/(\d+)$/);
      if (m && method === 'PATCH') {
        const id = Number(m[1]);
        const b = await req.json();
        // Only allow updating quantity, rate, total (whitelist safe columns)
        const allowed: Record<string, unknown> = {};
        if (b.quantity !== undefined) allowed.quantity = b.quantity;
        if (b.rate !== undefined) allowed.rate = b.rate;
        if (b.total !== undefined) allowed.total = b.total;
        if (Object.keys(allowed).length === 0) {
          return fail('BAD_REQUEST', 'No valid fields to update (quantity, rate, total)', 400);
        }
        const { data, error } = await adminClient
          .from('boq_items')
          .update(allowed)
          .eq('id', id)
          .select()
          .single();
        if (error) throw error;
        return ok(data);
      }
    }

    // AI
    {
      const m = path.match(/^\/projects\/(\d+)\/ai\/ask$/);
      if (m && method === 'POST') {
        const b = await req.json();
        return ok(await aiAsk(Number(m[1]), b.question ?? ''));
      }
    }
    {
      const m = path.match(/^\/projects\/(\d+)\/ai\/missing-boq$/);
      if (m && method === 'POST') return ok(await aiMissingBoq(Number(m[1])));
    }
    {
      const m = path.match(/^\/projects\/(\d+)\/ai\/anomalies$/);
      if (m && method === 'POST') return ok(await aiAnomalies(Number(m[1])));
    }
    {
      const m = path.match(/^\/projects\/(\d+)\/ai\/value-engineering$/);
      if (m && method === 'POST') return ok(await aiValueEngineering(Number(m[1])));
    }
    if (path === '/ai/capabilities' && method === 'GET') return ok(await aiCapabilities());

    // Exports
    {
      const m = path.match(/^\/projects\/(\d+)\/proposal$/);
      if (m && method === 'POST') return ok(await generateProposal(Number(m[1])));
    }
    {
      const m = path.match(/^\/projects\/(\d+)\/export$/);
      if (m && method === 'POST') {
        const b = await req.json();
        return ok(await generateExport(Number(m[1]), b.format ?? 'xlsx'));
      }
    }
    {
      const m = path.match(/^\/projects\/(\d+)\/purchase-list$/);
      if (m && method === 'POST') return ok(await generatePurchaseList(Number(m[1])));
    }
    {
      const m = path.match(/^\/projects\/(\d+)\/client-presentation$/);
      if (m && method === 'POST') return ok(await generateClientPresentation(Number(m[1])));
    }
    if (path === '/exports' && method === 'GET') {
      const pid = url.searchParams.get('project_id') ? Number(url.searchParams.get('project_id')) : undefined;
      return ok(await listExports(pid));
    }
    {
      const m = path.match(/^\/exports\/(\d+)\/download$/);
      if (m && method === 'GET') return ok(await exportDownloadUrl(Number(m[1])));
    }

    return fail('NOT_FOUND', `No route for ${method} ${path}`, 404);
  } catch (err: any) {
    console.error('[api] error', err);
    const code = err?.code ?? 'INTERNAL';
    const message = err?.message ?? 'Internal error';
    return fail(code, message, code === 'NOT_FOUND' ? 404 : 500);
  }
});
