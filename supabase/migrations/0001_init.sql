-- ═══════════════════════════════════════════════════════════════════════════════
-- Auto Cost Engine  —  initial schema (0001)
-- Apply from the Supabase dashboard → SQL editor → New query → paste → Run.
-- ═══════════════════════════════════════════════════════════════════════════════
--
-- This file defines every table the Edge Functions read/write. Run it once
-- against your Supabase project before deploying the functions. All tables
-- are owned by `postgres`; RLS is OFF because all writes go through Edge
-- Functions using the service-role key, never directly from the browser.

create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";

-- ── projects ───────────────────────────────────────────────────────────────
create table if not exists projects (
  id             bigserial primary key,
  name           text not null,
  client         text,
  location       text,
  status         text not null default 'draft' check (status in ('draft','in_progress','priced','sent','archived')),
  total          numeric(14,2),
  drawings_count integer not null default 0,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create index if not exists projects_status_idx  on projects (status);
create index if not exists projects_created_idx on projects (created_at desc);

-- ── drawings ──────────────────────────────────────────────────────────────
create table if not exists drawings (
  id            bigserial primary key,
  project_id    bigint not null references projects (id) on delete cascade,
  name          text not null,
  file_path     text,                          -- Supabase Storage object key
  file_size     bigint,
  width_mm      integer default 0,
  height_mm     integer default 0,
  status        text not null default 'uploaded' check (status in ('uploaded','pending','processing','processed','error','detected')),
  created_at    timestamptz not null default now(),
  detected_at   timestamptz
);
create index if not exists drawings_project_idx on drawings (project_id, created_at desc);

-- ── detected_objects ──────────────────────────────────────────────────────
create table if not exists detected_objects (
  id                bigserial primary key,
  project_id        bigint not null references projects (id) on delete cascade,
  drawing_id        bigint references drawings (id) on delete cascade,
  object_type       text not null,
  label             text,
  bbox              jsonb,                          -- {x,y,width,height} in normalised 0-1 OR mm
  bbox_x            numeric,
  bbox_y            numeric,
  length_mm         numeric,
  width_mm          numeric,
  area_mm2          numeric,
  confidence        numeric(4,3),
  trade             text,
  material_hint     text,
  quantity_estimate numeric,
  unit              text,
  detection_model   text,
  detection_source  text not null default 'ai' check (detection_source in ('rule','ai','hybrid')),
  created_at        timestamptz not null default now()
);
create index if not exists detected_objects_drawing_idx on detected_objects (drawing_id);
create index if not exists detected_objects_project_idx  on detected_objects (project_id);

-- ── boq_rules (master library) ───────────────────────────────────────────
create table if not exists boq_rules (
  id          bigserial primary key,
  key         text unique not null,
  object_type text not null,
  trade       text not null,
  category    text,
  unit        text,
  rate        numeric(12,2),
  material    text,
  keywords    text,
  active      boolean not null default true,
  ruleset_version text not null default 'office_india_v1'
);
create index if not exists boq_rules_type_idx on boq_rules (object_type);

-- ── boq_items (per-project derived lines) ───────────────────────────────
create table if not exists boq_items (
  id            bigserial primary key,
  project_id    bigint not null references projects (id) on delete cascade,
  drawing_id    bigint references drawings (id) on delete cascade,
  detected_object_id bigint references detected_objects (id) on delete set null,
  description   text not null,
  location      text,
  trade         text,
  material_id   bigint,
  material_name text,
  quantity      numeric(12,3) not null,
  unit          text,
  rate          numeric(12,2),
  total         numeric(14,2),
  rule_id       bigint references boq_rules (id),
  ruleset_version text,
  created_at    timestamptz not null default now()
);
create index if not exists boq_items_project_idx on boq_items (project_id, trade);

-- ── cost_versions (snapshot per compute) ────────────────────────────────
create table if not exists cost_versions (
  id                bigserial primary key,
  project_id        bigint not null references projects (id) on delete cascade,
  version_label     text not null,
  ruleset_version   text,
  materials_total   numeric(14,2),
  labour_total      numeric(14,2),
  transport_total   numeric(14,2),
  overheads_total   numeric(14,2),
  subtotal          numeric(14,2),
  markup_pct        numeric(5,2),
  markup_amount     numeric(14,2),
  contingency_pct   numeric(5,2),
  contingency_amount numeric(14,2),
  total             numeric(14,2) not null,
  breakdown         jsonb,
  created_at        timestamptz not null default now()
);
create index if not exists cost_versions_project_idx on cost_versions (project_id, created_at desc);

-- ── materials (catalogue) ────────────────────────────────────────────────
create table if not exists materials (
  id              bigserial primary key,
  name            text not null,
  brand           text,
  sku             text,
  category        text,
  unit            text not null default 'sft',
  rate            numeric(12,2) not null default 0,
  gst_rate        numeric(5,2) default 18,
  vendor_name     text,
  lead_time_days  integer default 7,
  warranty        text,
  fire_rating     text,
  is_preferred    boolean default false,
  thumbnail_url   text,
  active          boolean default true,
  created_at      timestamptz not null default now()
);
create index if not exists materials_category_idx on materials (category);

-- ── vendors ──────────────────────────────────────────────────────────────
create table if not exists vendors (
  id          bigserial primary key,
  name        text not null,
  city        text,
  gst         text,
  contact     text,
  active      boolean default true,
  created_at  timestamptz not null default now()
);

-- ── labour_rates ──────────────────────────────────────────────────────────
create table if not exists labour_rates (
  id           bigserial primary key,
  trade        text not null,
  category     text,
  rate         numeric(12,2) not null,
  unit         text not null default 'sqft',
  productivity  numeric(12,3),
  notes        text
);

-- ── cost_history (audit log) ──────────────────────────────────────────────
create table if not exists cost_history (
  id          bigserial primary key,
  project_id  bigint references projects (id) on delete cascade,
  action      text not null,
  export_type text,
  file_url    text,
  meta        jsonb,
  exported_at timestamptz not null default now()
);

-- ── exports (deliverable artefacts) ──────────────────────────────────────
create table if not exists exports (
  id           bigserial primary key,
  project_id   bigint references projects (id) on delete cascade,
  kind         text not null,                       -- 'proposal' | 'xlsx' | 'pdf' | 'purchase-list' | 'client-presentation'
  title        text,
  format       text,
  download_url text,
  meta         jsonb,
  created_at   timestamptz not null default now()
);

-- ── touched_at trigger to keep projects.updated_at honest ────────────────
create or replace function touch_project() returns trigger language plpgsql as $$
begin
  update projects set updated_at = now() where id = coalesce(new.project_id, old.project_id);
  return null;
end $$;

drop trigger if exists drawings_touch on drawings;
create trigger drawings_touch after insert or update or delete on drawings
  for each row execute function touch_project();

drop trigger if exists boq_items_touch on boq_items;
create trigger boq_items_touch after insert or update or delete on boq_items
  for each row execute function touch_project();
