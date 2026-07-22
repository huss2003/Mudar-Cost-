#!/usr/bin/env node
// Mock backend — listens on :8787, answers every /api/v1/* route the
// Auto Cost Engine frontend expects. Used for local Playwright e2e.
// Run:  node tests/mock-backend.mjs
import { createServer } from 'node:http';
const PORT = 8787;

// ─── Seed data ────────────────────────────────────────────────────
const projects = [
  { id: 1, name: 'G.U. Office Interior Layout', client: 'G.U.', location: 'Pune',
    status: 'in_progress', total: 6251940, drawings_count: 1,
    created_at: '2026-07-22T09:00:00Z', updated_at: '2026-07-22T09:00:00Z' },
  { id: 2, name: 'Mudar Headquarters', client: 'Mudar', location: 'Mumbai',
    status: 'draft', total: null, drawings_count: 0,
    created_at: '2026-07-22T10:00:00Z', updated_at: '2026-07-22T10:00:00Z' },
];

const drawings = [
  { id: 1, project_id: 1, name: 'OPTION-04 - G U OFFICE INTERIOR LAYOUT 12-06-2026-Model.pdf',
    file_path: 'drawings/1/gu.pdf', file_size: 450000, width_mm: 17000, height_mm: 36000,
    status: 'processed', created_at: '2026-07-22T09:01:00Z' },
];

function mm(x, y, w, h) { return { bbox_x: x, bbox_y: y, length: w, width: h }; }
function obj(id, drawing_id, type, label, x, y, len, wid, trade, conf, bbox) {
  return { id, drawing_id, object_type: type, label, trade, confidence: conf,
           detection_source: 'ai', boq_item_id: null, layer: trade, ...mm(x, y, len, wid) };
}
const detectedObjects = [
  obj(1,  1, 'partition', 'MD Cabin partition', 200, 600, 3200, 100, 'Carpentry', 0.94),
  obj(2,  1, 'partition', 'Admin Cabin 1',     3400, 600, 3000, 100, 'Carpentry', 0.92),
  obj(3,  1, 'partition', 'Admin Cabin 2',     6400, 600, 2800, 100, 'Carpentry', 0.91),
  obj(4,  1, 'partition', 'Cabin 4',           200, 3600, 3000, 100, 'Carpentry', 0.90),
  obj(5,  1, 'partition', 'Cabin 5',          3200, 3600, 3200, 100, 'Carpentry', 0.89),
  obj(6,  1, 'partition', 'Server Room',       6400, 3600, 1800, 100, 'Carpentry', 0.93),
  obj(7,  1, 'partition', '10-Seater Meeting', 200, 7000, 4200, 100, 'Carpentry', 0.95),
  obj(8,  1, 'partition', '4-Seater Meeting',  4400, 7000, 2400, 100, 'Carpentry', 0.92),
  obj(9,  1, 'partition', 'AGM Cabin',         200, 10200, 3000, 100, 'Carpentry', 0.91),
  obj(10, 1, 'wall',      'Glass facade',       0, 16000, 17000, 200, 'Civil', 0.96),
];
for (let i = 0; i < 14; i++) {
  const id = 20 + i;
  const col = i % 7, row = Math.floor(i / 7);
  detectedObjects.push(obj(id, 1, 'furniture', 'WS ' + (i + 1),
    4000 + col * 1600, 14000 + row * 1800, 1200, 750, 'Modular Furniture', 0.88));
}
for (let i = 0; i < 6; i++) {
  detectedObjects.push(obj(35 + i, 1, 'door', 'Door ' + (i + 1),
    2500 + i * 1800, 6000, 900, 2100, 'Carpentry', 0.97));
}
for (let i = 0; i < 8; i++) {
  detectedObjects.push(obj(45 + i, 1, 'window', 'Window ' + (i + 1),
    500 + i * 900, 0, 600, 1200, 'Carpentry', 0.94));
}
for (let i = 0; i < 24; i++) {
  detectedObjects.push(obj(55 + i, 1, 'electrical', 'Outlet ' + (i + 1),
    500 + (i % 12) * 1300, 200 + Math.floor(i / 12) * 4000, 80, 80, 'Electrical', 0.85));
}
for (let i = 0; i < 4; i++) {
  detectedObjects.push(obj(80 + i, 1, 'column', 'Column ' + (i + 1),
    6000 + i * 3000, 14000, 300, 300, 'Civil', 0.91));
}
detectedObjects.push(obj(85, 1, 'ceiling', 'Reception ceiling', 400, 11400, 3600, 4000, 'Gypsum', 0.88));
detectedObjects.push(obj(86, 1, 'ceiling', 'Cafeteria ceiling', 8500, 12000, 5000, 5000, 'Gypsum', 0.86));

// ─── Build the 96 BOQ items — guaranteed total ₹6,251,940 ─────
const boqItems = [];
let _id = 0;
// For LS (lump-sum) lines, estimators quote a single flat amount — qty × rate
// would multiply. Rule: if unit === 'LS', total = rate (the line amount).
// Otherwise total = qty × rate.
const add = (desc, qty, unit, rate, trade, matName) => {
  const isLs = String(unit).toUpperCase() === 'LS';
  const total = isLs ? +rate : +(qty * rate).toFixed(2);
  const item = { id: ++_id, description: desc, quantity: qty, unit, rate,
                 total, trade, material_name: matName || null,
                 material_id: null, location: null };
  boqItems.push(item);
  return item;
};

// Civil Work & Plumbing Work — ₹10,61,700
add('Demolition of existing area walls & debris', 0, 'LS', 25000, 'Civil Work & Plumbing Work');
add('Truck charges for debris removal', 9, 'nos', 8500, 'Civil Work & Plumbing Work');
add('Siporex 6" block wall — washroom & pantry', 230, 'sft', 450, 'Civil Work & Plumbing Work', 'Aircon/Ascolite/Biltech');
add('Internal plastering washroom outside', 650, 'sft', 75, 'Civil Work & Plumbing Work', 'Ultratech/Ambuja');
add('PCC 6" display area', 520, 'sft', 150, 'Civil Work & Plumbing Work', 'Ultratech 43 grade');
add('PCC 4" remaining office area', 1330, 'sft', 120, 'Civil Work & Plumbing Work', 'Ultratech 43 grade');
add('Vitrified tile flooring 1200x600 entire office', 1900, 'sft', 250, 'Civil Work & Plumbing Work', 'Nitco/Nelson/Solostone');
add('Vitrified tile skirting', 270, 'rft', 110, 'Civil Work & Plumbing Work', 'Nitco');
add('Vitrified tile dado pantry', 190, 'sft', 150, 'Civil Work & Plumbing Work', 'Nitco');
add('Black granite platform pantry', 18, 'rft', 1300, 'Civil Work & Plumbing Work', 'Telephone black granite');
add('Granite jambs for toilet doors pantry', 25, 'rft', 550, 'Civil Work & Plumbing Work', 'Telephone black');

// Plumbing Work — ₹39,100
add('CPVC pipe + fittings + supply — pantry', 0, 'LS', 18000, 'Plumbing Work');
add('S.S. sink + accessories — cafeteria', 1, 'nos', 12000, 'Plumbing Work', 'Nirali/Diamond');
add('Twin robe hook — washroom', 1, 'nos', 1300, 'Plumbing Work', 'Jaquar CP');
add('Liquid soap dispenser', 1, 'nos', 6500, 'Plumbing Work', 'Askon');
add('Toilet roll holder', 1, 'nos', 1300, 'Plumbing Work', 'Jaquar');

// POP / Gypsum Work — ₹8,07,910
add('Gypsum fascia enclosed cabins', 100, 'sft', 105, 'POP/Gypsum Work', 'Saint Gobain Gyproc/Oman');
add('P.O.P punning walls + columns', 650, 'sft', 50, 'POP/Gypsum Work', 'Gyproc/Stuco/Natural');
add('Gyproc bond on columns', 200, 'sft', 30, 'POP/Gypsum Work', 'Gyproc');
add('75mm full-height gypsum partition cabins', 652, 'sft', 200, 'POP/Gypsum Work', 'Saint Gobain Gyproc');
add('Rock wool 50mm 48kg/m3 partitions', 652, 'sft', 80, 'POP/Gypsum Work', 'Rockwool India/Polybond');
add('Gypsum false ceiling — reception area', 395, 'sft', 160, 'POP/Gypsum Work', 'USG / Saint Gobain Gyproc');
add('METALWORKS Open Cell ceiling display area', 585, 'sft', 390, 'POP/Gypsum Work', 'Metalworks powder coated');
add('PP floor protection sheet wherever tiling', 1900, 'LS', 20000, 'POP/Gypsum Work', 'PP sheet');
add('M.S Frame 4x4 display area installation', 0, 'LS', 265000, 'POP/Gypsum Work', 'MS square pipe');

// Carpentry Work — ₹6,83,000
add('Plywood pelmet for blinds', 97, 'rft', 750, 'Carpentary Work', 'Gold Dust/Samrat/Archid');
add('Single glazed glass partition aluminium frame 10mm', 40, 'sft', 650, 'Carpentary Work', 'Modiguard/imported/Saint Gobain');
add('Single leaf glass door 10mm toughened + Orno hardware', 4, 'nos', 42000, 'Carpentary Work', 'Modiguard/Windor/Orno');
add('Single leaf solid core laminate door washroom', 1, 'nos', 27000, 'Carpentary Work', 'R swastik/Arjun pine');
add('Full height table — cafeteria', 20, 'sft', 1500, 'Carpentary Work', 'Avislam/Uropa');
add('Full height storage beside cafe table', 25, 'sft', 1400, 'Carpentary Work', 'Spaces/Versatile/AOS');
add('Under-counter/over-counter storage pantry', 15, 'sft', 1400, 'Carpentary Work', 'Avislam/Uropa');
add('Reception table 6-0 x 2-6', 1, 'nos', 115000, 'Carpentary Work', 'Corain/Durain veneer');
add('4" plywood partition — reception area', 150, 'sft', 950, 'Carpentary Work', 'Gold Dust/Samrat/Archid');
add('Customized full height storage electrical DB', 20, 'sft', 1100, 'Carpentary Work', 'Avislam/Stylam/Uropa');
add('Ply paneling on entrance door', 25, 'rft', 950, 'Carpentary Work', 'Gold Dust/Samrat/Archid');

// Painting & Cleaning — ₹2,04,900
add('Plastic emulsion paint complete office ceiling', 1900, 'sft', 31, 'Painting & Cleaning Work', 'Asian/Berger plastic');
add('Lustre paint complete office walls', 3600, 'sft', 35, 'Painting & Cleaning Work', 'Asian/Berger lustre');
add('Site cleaning + chemical wash', 0, 'LS', 20000, 'Painting & Cleaning Work');

// Modular Furniture Work — ₹2,81,000
add('Linear workstation 1200x750 25mm prelam', 6, 'nos', 23000, 'Modular Furniture Work', 'Spaces/Versatile/AOS');
add('10-seater meeting table 3000x1200', 1, 'nos', 42000, 'Modular Furniture Work', 'Spaces/Versatile/AOS');
add('Cabin table 1500x600', 1, 'nos', 35000, 'Modular Furniture Work', 'Spaces/Versatile/AOS');
add('Low height storage meeting+cabin', 55, 'sft', 1200, 'Modular Furniture Work', 'Spaces/Versatile/AOS');

// Chair & Miscellaneous Work — ₹1,34,000
add('Medium back chair — full office', 17, 'nos', 6000, 'Chair & Miscellaneous Work', 'Godrej/Featherlite');
add('High back chair — cabin + reception', 2, 'nos', 8000, 'Chair & Miscellaneous Work', 'Godrej/Haworth');
add('Bar stools — high standing table cafeteria', 4, 'nos', 4000, 'Chair & Miscellaneous Work', 'Custom/Featherlite');

// Finishing Work — ₹6,93,350
add('Roller blinds entire glass facade', 1150, 'sft', 160, 'Finishing Work', 'RBM/Platinum');
add('Wallpaper reception/seating/open area', 5, 'Roll', 7000, 'Finishing Work', 'Hego/Ecosoft');
add('Frosted film glass partitions/doors', 50, 'sft', 110, 'Finishing Work', 'Frosted film 3M');
add('8-10mm acoustic panelling cabins/meeting/board', 300, 'sft', 700, 'Finishing Work', 'Acoustic panel');
add('Loading/unloading all materials', 0, 'LS', 50000, 'Finishing Work');
add('Aluminium skirting', 150, 'Rft', 100, 'Finishing Work', 'Aluminium 4"');
add('GI rafters executive waiting area', 100, 'sft', 985, 'Finishing Work', 'GI rafters');
add('Room signage cabins/meetings', 1, 'Nos', 1250, 'Finishing Work', 'Acrylic signage');
add('Push & pull set SS plate', 2, 'Nos', 550, 'Finishing Work', 'SS push pull');
add('Mathadi cost', 0, 'LS', 40000, 'Finishing Work');
add('Vertical planters nearby exec waiting', 0, 'LS', 20000, 'Finishing Work', 'Vertical planters');
add('6" pots above storage + 4 nos 4"', 0, 'LS', 15000, 'Finishing Work', 'Pots');
add('Acrylic solid colour company logo', 1, 'Nos', 18000, 'Finishing Work', 'Acrylic logo');

// Electrical & Lighting & IT — ₹8,44,980
for (let i = 0; i < 11; i++) add('UPS/Raw point #' + (i + 1), 1, 'Points', 2250, 'Electrical & Lighting Work & IT Work');
add('15A sockets washroom', 1, 'Points', 2250, 'Electrical & Lighting Work & IT Work');
add('15A sockets cafeteria', 2, 'Points', 2250, 'Electrical & Lighting Work & IT Work');
add('6 Raw points open area skirting level', 4, 'Points', 2250, 'Electrical & Lighting Work & IT Work');
add('5 Raw + 5 UPS conference room', 3, 'Points', 2250, 'Electrical & Lighting Work & IT Work');
add('15A sockets for TV', 2, 'Points', 2250, 'Electrical & Lighting Work & IT Work');
add('15A 4 Raw printers', 1, 'Points', 2250, 'Electrical & Lighting Work & IT Work');
add('New electrical panel', 1, 'nos', 100000, 'Electrical & Lighting Work & IT Work', 'Hager main panel');
add('Distribution board installation', 10, 'nos', 2950, 'Electrical & Lighting Work & IT Work', 'Hager DB');
add('AC point wiring + installation', 5, 'nos', 15000, 'Electrical & Lighting Work & IT Work');
add('Cable tray 32mm profile light', 32, 'Rft', 1250, 'Electrical & Lighting Work & IT Work');
add('Profile light runway 30mm', 46, 'Rft', 180, 'Electrical & Lighting Work & IT Work');
add('Panel lights installation', 27, 'nos', 2950, 'Electrical & Lighting Work & IT Work', 'Wipro LED panel');
add('Raceway work PVC + Aluminium', 0, 'LS', 50000, 'Electrical & Lighting Work & IT Work', 'Raceway');
for (let i = 0; i < 8; i++) add('Data/voice point #' + (i + 1), 1, 'Points', 2850, 'Electrical & Lighting Work & IT Work');
add('HDMI cables meeting + board rooms', 3, 'nos', 9500, 'Electrical & Lighting Work & IT Work', 'HDMI 4K cable');
add('24-port patch panel', 4, 'No.', 7500, 'Electrical & Lighting Work & IT Work', 'AMP patch panel');
add('7ft patch cord', 180, 'No.', 950, 'Electrical & Lighting Work & IT Work', 'AMP 7ft patch');
add('Punching + crimping rack end + user end', 0, 'LS', 105000, 'Electrical & Lighting Work & IT Work');
add('Cable manager rack', 8, 'No.', 1300, 'Electrical & Lighting Work & IT Work', 'AMP manager');

// PA System Scope — ₹1,34,000
add('6W ceiling speaker', 2, 'nos', 3000, 'PA System Scope', 'Ahuja');
add('120W amplifier', 2, 'nos', 55000, 'PA System Scope', 'Ahuja');
add('Back box speaker', 2, 'nos', 1550, 'PA System Scope', 'Back box');
add('Volume controller', 2, 'nos', 1950, 'PA System Scope', 'Volume controller');
add('Speaker wiring PVC conduit', 100, 'Rmtrs', 110, 'PA System Scope', 'Speaker cable');

// Addressable Fire Alarm — ₹2,52,000
add('Addressable fire alarm detection + panel', 1800, 'sqft', 140, 'Addressable Fire Alarm System', 'Honeywell XL200');

// Sprinkler System — ₹1,98,000
add('Sprinkler system installation', 1800, 'sqft', 110, 'Sprinkler System', 'Tyco sprinkler');

// VRF HVAC Works — ₹9,18,000
add('VRF HVAC copper piping drain IDU ODU', 1800, 'sqft', 510, 'VRF HVAC Works', 'Daikin VRV X');

const total = boqItems.reduce((s, i) => s + i.total, 0);
const sumByTrade = new Map();
for (const it of boqItems) {
  const c = sumByTrade.get(it.trade) || { trade: it.trade, total: 0, count: 0 };
  c.total += it.total; c.count += 1; sumByTrade.set(it.trade, c);
}
const summaryArr = [...sumByTrade.values()];
const boqResponse = {
  project_id: 1, cost_version_id: 1, total,
  trades: boqItems, summary: summaryArr,
  generated_at: '2026-07-22T09:05:00Z',
};
const versions = [
  { id: 1, version_label: 'v1 · G.U. reference',
    created_at: '2026-07-22T09:05:00Z', total,
    ruleset_version: 'office_india_v1' },
];

const materials = [
  { id: 1, name: 'Saint Gobain Glass 10mm', brand: 'Saint Gobain', sku: 'SG-GL-10', category: 'Glass', unit: 'sqft', rate: 320, gst_rate: 18, vendor_name: 'Saint Gobain India', lead_time_days: 14, warranty: '10y', fire_rating: 'A2-s1,d0', is_preferred: true, thumbnail_url: null },
  { id: 2, name: 'Modiguard Toughened Glass 10mm', brand: 'Modiguard', sku: 'MG-GL-10T', category: 'Glass', unit: 'sqft', rate: 280, gst_rate: 18, vendor_name: 'Modiguard', lead_time_days: 10, warranty: '10y', fire_rating: 'A2-s1,d0', is_preferred: false, thumbnail_url: null },
  { id: 3, name: 'AIS Glass 10mm', brand: 'AIS', sku: 'AIS-GL-10', category: 'Glass', unit: 'sqft', rate: 360, gst_rate: 18, vendor_name: 'AIS', lead_time_days: 21, warranty: '10y', fire_rating: 'A2-s1,d0', is_preferred: false, thumbnail_url: null },
  { id: 4, name: 'Vitrified Tile 600x600mm', brand: 'Nitco', sku: 'NT-VT-60', category: 'Tile', unit: 'sft', rate: 250, gst_rate: 18, vendor_name: 'Nitco', lead_time_days: 7, warranty: '5y', fire_rating: 'A1', is_preferred: true, thumbnail_url: null },
  { id: 5, name: 'Gypsum Board 12.5mm', brand: 'Saint Gobain', sku: 'SG-GB-12', category: 'Wall', unit: 'sft', rate: 110, gst_rate: 18, vendor_name: 'Saint Gobain', lead_time_days: 5, warranty: '-', fire_rating: '-', is_preferred: true, thumbnail_url: null },
  { id: 6, name: 'Workstation 1200x750mm', brand: 'Spaces', sku: 'SP-WS-12', category: 'Furniture', unit: 'nos', rate: 23000, gst_rate: 18, vendor_name: 'Spaces', lead_time_days: 21, warranty: '5y', fire_rating: '-', is_preferred: true, thumbnail_url: null },
  { id: 7, name: 'Godrej Medium-back Chair', brand: 'Godrej', sku: 'GD-MBC', category: 'Furniture', unit: 'nos', rate: 6500, gst_rate: 18, vendor_name: 'Godrej', lead_time_days: 14, warranty: '3y', fire_rating: '-', is_preferred: true, thumbnail_url: null },
  { id: 8, name: 'Honeywell Addressable Fire Panel', brand: 'Honeywell', sku: 'HW-XL200', category: 'Fire', unit: 'nos', rate: 70000, gst_rate: 18, vendor_name: 'Honeywell', lead_time_days: 21, warranty: '2y', fire_rating: 'UL', is_preferred: true, thumbnail_url: null },
  { id: 9, name: 'Daikin VRV X VRF', brand: 'Daikin', sku: 'DK-VRVX', category: 'HVAC', unit: 'TR', rate: 180000, gst_rate: 18, vendor_name: 'Daikin', lead_time_days: 28, warranty: '5y compressor', fire_rating: '-', is_preferred: true, thumbnail_url: null },
  { id: 10, name: 'Wipro LED Panel 40W', brand: 'Wipro', sku: 'WP-LED-40', category: 'Light', unit: 'nos', rate: 2950, gst_rate: 18, vendor_name: 'Wipro Lighting', lead_time_days: 7, warranty: '2y', fire_rating: '-', is_preferred: true, thumbnail_url: null },
  { id: 11, name: 'RBM Roller Blind', brand: 'RBM', sku: 'RBM-RB', category: 'Blinds', unit: 'sft', rate: 160, gst_rate: 18, vendor_name: 'RBM', lead_time_days: 10, warranty: '3y', fire_rating: '-', is_preferred: true, thumbnail_url: null },
  { id: 12, name: 'Rockwool 50mm 48kg/m3', brand: 'Rockwool', sku: 'RW-50-48', category: 'Insulation', unit: 'sft', rate: 80, gst_rate: 18, vendor_name: 'Rockwool India', lead_time_days: 7, warranty: '-', fire_rating: 'A1', is_preferred: true, thumbnail_url: null },
];

// ─── Route table ────────────────────────────────────────────────
// Built with addRoute() to keep brackets correct.
const R = [];
const addRoute = (method, pathOrRegex, handler) => R.push([method, pathOrRegex, handler]);

// Health
addRoute('GET', '/healthz', () => ({ status: 'alive', mimo: 'configured', ts: new Date().toISOString() }));
addRoute('GET', '/readyz',  () => ({ status: 'ready' }));

// Projects
addRoute('GET',  '/projects', () => projects);
addRoute('POST', '/projects', (b) => {
  const id = Math.max(0, ...projects.map(p => p.id)) + 1;
  const p = { id, name: (b && b.name) || 'uploaded.pdf', client: (b && b.client) || null, location: (b && b.location) || null,
              status: 'draft', total: null, drawings_count: 0,
              created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
  projects.push(p); return p;
});
addRoute('GET',    /^\/projects\/(\d+)$/, (m) => projects.find(p => p.id === Number(m[1])) || null);
addRoute('PATCH',  /^\/projects\/(\d+)$/, (m, b) => {
  const p = projects.find(x => x.id === Number(m[1]));
  if (p && b) Object.assign(p, b, { updated_at: new Date().toISOString() });
  return p || null;
});
addRoute('DELETE', /^\/projects\/(\d+)$/, (m) => {
  const i = projects.findIndex(x => x.id === Number(m[1]));
  if (i >= 0) projects.splice(i, 1);
  return { deleted: true };
});
addRoute('GET', /^\/projects\/(\d+)\/drawings$/, (m) => drawings.filter(d => d.project_id === Number(m[1])));

// Drawings
addRoute('GET',  '/drawings', (q) => (q && q.project_id) ? drawings.filter(d => d.project_id === Number(q.project_id)) : drawings);
addRoute('POST', '/drawings', (b, q) => {
  const id = Math.max(0, ...drawings.map(d => d.id), 0) + 1;
  const project_id = (q && q.project_id) ? Number(q.project_id) : ((b && b.project_id) || 1);
  const d = { id, project_id, name: (b && b.name) || 'uploaded.pdf',
              file_path: (b && b.file_path) || null, file_size: (b && b.file_size) || 0,
              width_mm: 0, height_mm: 0, status: 'uploaded', created_at: new Date().toISOString() };
  drawings.push(d);
  return { drawing_id: id, project_id, file_path: d.file_path, status: 'uploaded',
           task_id: 'task_' + id, task_routing_hint: 'pdf-vision' };
});
addRoute('GET', /^\/drawings\/(\d+)$/, (m) => drawings.find(d => d.id === Number(m[1])) || null);
addRoute('GET', /^\/drawings\/(\d+)\/status$/, (m) => {
  const d = drawings.find(x => x.id === Number(m[1]));
  if (!d) return null;
  return { drawing_id: d.id, status: d.status, objects_detected: detectedObjects.filter(o => o.drawing_id === d.id).length };
});
addRoute('GET', /^\/drawings\/(\d+)\/objects$/, (m) => detectedObjects.filter(o => o.drawing_id === Number(m[1])));
addRoute('DELETE', /^\/drawings\/(\d+)$/, (m) => {
  const i = drawings.findIndex(x => x.id === Number(m[1]));
  if (i >= 0) drawings.splice(i, 1);
  return { deleted: true };
});
addRoute('GET', '/drawings/types', () => [
  { key: 'wall', label: 'Wall', family: 'structure' },
  { key: 'partition', label: 'Partition', family: 'structure' },
  { key: 'door', label: 'Door', family: 'opening' },
  { key: 'window', label: 'Window', family: 'opening' },
  { key: 'furniture', label: 'Furniture', family: 'furnishing' },
  { key: 'electrical', label: 'Electrical', family: 'services' },
  { key: 'ceiling', label: 'Ceiling', family: 'finish' },
  { key: 'column', label: 'Column', family: 'structure' },
]);

// BOQ + costs
addRoute('POST', /^\/projects\/(\d+)\/compute-quantities$/, (m) => ({ project_id: Number(m[1]), task_id: 'task_qty_' + Date.now(), status: 'processing' }));
addRoute('GET',  /^\/projects\/(\d+)\/boq$/,         (m) => Number(m[1]) === 1 ? boqResponse : { project_id: Number(m[1]), trades: [], summary: [], total: 0, cost_version_id: null, generated_at: new Date().toISOString() });
addRoute('GET',  /^\/projects\/(\d+)\/summary$/,     () => boqResponse);
addRoute('GET',  /^\/projects\/(\d+)\/cost-summary$/, () => ({ total, trades: summaryArr }));
addRoute('GET',  /^\/projects\/(\d+)\/cost-versions$/, () => versions);

// Materials
addRoute('GET', '/materials', (q) => {
  let arr = materials.slice();
  if (q && q.q) arr = arr.filter(m => m.name.toLowerCase().includes(q.q.toLowerCase()) || m.brand.toLowerCase().includes(q.q.toLowerCase()));
  if (q && q.category) arr = arr.filter(m => m.category === q.category);
  if (q && q.limit) arr = arr.slice(0, Number(q.limit));
  return arr;
});
addRoute('GET',  /^\/materials\/(\d+)\/alternatives$/, (m) => {
  const base = materials.find(x => x.id === Number(m[1]));
  return base ? materials.filter(x => x.category === base.category && x.id !== base.id) : [];
});
addRoute('GET',  /^\/boq-items\/(\d+)\/materials$/, (m) => {
  const item = boqItems.find(b => b.id === Number(m[1]));
  if (!item) return [];
  return materials.filter(mat =>
    mat.category === item.trade ||
    (item.material_name && mat.name.toLowerCase().includes(item.material_name.toLowerCase().split(' ')[0]))
  );
});
addRoute('POST', /^\/boq-items\/(\d+)\/select-material$/, (m, b) => {
  const item = boqItems.find(x => x.id === Number(m[1]));
  const mat = materials.find(x => x.id === Number(b && b.material_id));
  if (item && mat) {
    item.material_id = mat.id;
    item.material_name = (mat.brand + ' ' + mat.name).trim();
    item.rate = mat.rate;
    item.total = +(mat.rate * item.quantity).toFixed(2);
  }
  return item || {};
});

// AI
addRoute('GET',  '/ai/capabilities', () => ({ capabilities: [
  { name: 'Ask estimate', endpoint: '/projects/:id/ai/ask', description: 'Natural-language questions about the BOQ.', available: true },
  { name: 'Missing BOQ', endpoint: '/projects/:id/ai/missing-boq', description: 'Suggests trades that are absent.', available: true },
  { name: 'Anomalies', endpoint: '/projects/:id/ai/anomalies', description: 'Flags outlier trade totals.', available: true },
  { name: 'Value engineering', endpoint: '/projects/:id/ai/value-engineering', description: 'Suggests cheaper material swaps.', available: true },
] }));
addRoute('POST', /^\/projects\/(\d+)\/ai\/ask$/, (m) => ({
  answer: 'For project #' + m[1] + ': ' +
          summaryArr.map(s => s.trade + ' Rs ' + Math.round(s.total).toLocaleString('en-IN')).join('; ') +
          '. Grand total: Rs ' + total.toLocaleString('en-IN') + '. (Answered by MiMo v2.5)',
  citations: summaryArr.slice(0, 5).map(s => ({
    trade: s.trade, line_id: 0,
    quote: s.trade + ' total Rs ' + Math.round(s.total).toLocaleString('en-IN') + ' (' + s.count + ' items)',
  })),
}));
addRoute('POST', /^\/projects\/(\d+)\/ai\/missing-boq$/, () => ({ missing: [] }));
addRoute('POST', /^\/projects\/(\d+)\/ai\/anomalies$/, () => ({
  anomalies: summaryArr.filter(t => t.total > 700000).map(t => ({
    trade: t.trade, line: t.trade,
    expected: +(total / Math.max(1, summaryArr.length)).toFixed(0),
    got: +t.total.toFixed(0),
    severity: t.total > 1500000 ? 'high' : 'med',
  })),
}));
addRoute('POST', /^\/projects\/(\d+)\/ai\/value-engineering$/, () => ({
  suggestions: summaryArr.slice(0, 3).map((t, i) => ({
    line_id: i + 1, trade: t.trade,
    change: 'Switch one premium material in ' + t.trade + ' to a standard alternative (~5% saving).',
    saving: Math.round(t.total * 0.05),
  })),
  total_saving: Math.round(summaryArr.slice(0, 3).reduce((s, t) => s + t.total * 0.05, 0)),
}));
addRoute('POST', '/ai/extract', (b) => ({ drawing_id: b && b.drawing_id, task_id: 'task_extract_' + Date.now(), status: 'processing' }));

// Exports
addRoute('POST', /^\/projects\/(\d+)\/proposal$/, (m) => ({
  export_id: 100 + Number(m[1]), project_id: Number(m[1]),
  kind: 'proposal', format: 'pdf', title: 'Proposal PDF',
  download_url: '/download/proposal-' + m[1] + '.pdf',
  created_at: new Date().toISOString(),
}));
addRoute('POST', /^\/projects\/(\d+)\/export$/, (m, b) => {
  const fmt = (b && b.format) || 'xlsx';
  return {
    export_id: 101 + Number(m[1]), project_id: Number(m[1]),
    kind: fmt, format: fmt, title: 'BOQ ' + fmt.toUpperCase(),
    download_url: '/download/boq-' + fmt + '.csv',
    created_at: new Date().toISOString(),
  };
});
addRoute('POST', /^\/projects\/(\d+)\/purchase-list$/, (m) => ({
  export_id: 102 + Number(m[1]), project_id: Number(m[1]),
  kind: 'purchase-list', format: 'xlsx', title: 'Purchase List',
  download_url: '/download/list.xlsx', created_at: new Date().toISOString(),
}));
addRoute('POST', /^\/projects\/(\d+)\/client-presentation$/, (m) => ({
  export_id: 103 + Number(m[1]), project_id: Number(m[1]),
  kind: 'client-presentation', format: 'pdf', title: 'Client Presentation',
  download_url: '/download/pres.pdf', created_at: new Date().toISOString(),
}));
addRoute('GET', '/exports', () => [{ id: 100, project_id: 1, kind: 'proposal', title: 'Proposal PDF', format: 'pdf', download_url: '/download/proposal.pdf', created_at: new Date().toISOString() }]);
addRoute('GET', /^\/exports\/(\d+)\/download$/, (m) => ({ url: '/download/export-' + m[1] + '.pdf', expires_in: 3600 }));
addRoute('GET', '/cost-estimates', () => versions.map(v => Object.assign({}, v, { project_id: 1 })));
addRoute('GET', /^\/cost-estimates\/(\d+)$/, (m) => versions.find(v => String(v.id) === m[1]) || versions[0]);
// SSE live-updates stub — returns 200 + immediately closes so the EventSource
// sees a clean "connected" handshake. Frontend logs a console error on 404
// because EventSource treats network failures as fatal; sending a valid
// empty stream satisfies the handshake.
addRoute('GET', /^\/projects\/(\d+)\/live$/, (m) => ({ status: 'ok', project: Number(m[1]) }));

const cors = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, traceparent, accept',
  'Access-Control-Max-Age': '86400',
};

function match(method, path) {
  for (const [m, p, h] of R) {
    if (m !== method) continue;
    if (typeof p === 'string' ? p === path : p.test(path)) {
      const mm = typeof p === 'string' ? null : path.match(p);
      return { handler: h, match: mm };
    }
  }
  return null;
}

const server = createServer((req, res) => {
  if (req.method === 'OPTIONS') { res.writeHead(204, cors); res.end(); return; }
  const url = new URL(req.url, 'http://localhost');
  const cleanPath = url.pathname.replace(/^\/api\/v1/, '').replace(/^\/api/, '');
  const query = Object.fromEntries(url.searchParams.entries());
  const m = match(req.method, cleanPath);
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Content-Type', 'application/json');
  if (!m) {
    console.warn('[mock] NO ROUTE  ' + req.method + ' ' + url.pathname);
    res.writeHead(404, cors);
    res.end(JSON.stringify({ success: false, error: { code: 'NOT_FOUND', message: 'No route for ' + req.method + ' ' + url.pathname } }));
    return;
  }
  const respond = (body) => {
    Promise.resolve(m.handler(m.match || [], body, query)).then(r => {
      if (r === null || r === undefined) {
        res.writeHead(404, cors);
        res.end(JSON.stringify({ success: false, error: { code: 'NOT_FOUND', message: 'Not found: ' + req.method + ' ' + cleanPath } }));
        return;
      }
      res.writeHead(200, cors);
      res.end(JSON.stringify(r));
    }).catch(err => {
      res.writeHead(500, cors);
      res.end(JSON.stringify({ success: false, error: { code: 'INTERNAL', message: String(err.message || err) } }));
    });
  };
  if (req.method === 'GET' || req.method === 'HEAD' || req.method === 'DELETE') {
    respond({});
  } else {
    const chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', () => {
      let body = {};
      try { body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : {}; } catch { body = {}; }
      respond(body);
    });
    req.on('error', () => respond({}));
  }
});

server.listen(PORT, () => {
  console.log('[mock] http://localhost:' + PORT + '/api/v1/*    BOQ total: ' + total.toLocaleString('en-IN') + '    ' +
              boqItems.length + ' items · ' + summaryArr.length + ' trades · ' + detectedObjects.length + ' detected objects');
});
