import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabaseUrl = Deno.env.get('SUPABASE_URL')!
const supabaseKey = Deno.env.get('SUPABASE_ANON_KEY')!
const supabase = createClient(supabaseUrl, supabaseKey)

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

interface BOQItem {
  project_id: number
  drawing_id?: number
  trade: string
  category: string
  description: string
  material?: string
  unit: string
  quantity: number
  rate: number
  amount: number
  detected_object_id?: number
  rule_id?: number
}

// Default BOQ rules for common construction elements
const DEFAULT_RULES: Record<string, { category: string; unit: string; rate: number; material: string }> = {
  'wall': { category: 'Masonry', unit: 'm2', rate: 85.00, material: 'Concrete Block' },
  'interior_wall': { category: 'Masonry', unit: 'm2', rate: 75.00, material: 'Drywall' },
  'exterior_wall': { category: 'Masonry', unit: 'm2', rate: 120.00, material: 'Concrete Block' },
  'door': { category: 'Carpentry', unit: 'pcs', rate: 450.00, material: 'Timber' },
  'sliding_door': { category: 'Carpentry', unit: 'pcs', rate: 850.00, material: 'Aluminium' },
  'window': { category: 'Carpentry', unit: 'pcs', rate: 380.00, material: 'Aluminium' },
  'floor': { category: 'Flooring', unit: 'm2', rate: 65.00, material: 'Ceramic Tile' },
  'flooring': { category: 'Flooring', unit: 'm2', rate: 65.00, material: 'Ceramic Tile' },
  'ceiling': { category: 'Ceiling', unit: 'm2', rate: 55.00, material: 'Gypsum Board' },
  'column': { category: 'Structural', unit: 'pcs', rate: 1200.00, material: 'Reinforced Concrete' },
  'beam': { category: 'Structural', unit: 'm', rate: 350.00, material: 'Reinforced Concrete' },
  'pipe': { category: 'Plumbing', unit: 'm', rate: 45.00, material: 'PVC' },
  'fixture': { category: 'Plumbing', unit: 'pcs', rate: 280.00, material: 'Porcelain' },
  'sink': { category: 'Plumbing', unit: 'pcs', rate: 350.00, material: 'Stainless Steel' },
  'toilet': { category: 'Plumbing', unit: 'pcs', rate: 480.00, material: 'Porcelain' },
  'bathtub': { category: 'Plumbing', unit: 'pcs', rate: 1200.00, material: 'Acrylic' },
  'shower': { category: 'Plumbing', unit: 'pcs', rate: 650.00, material: 'Chrome' },
  'electrical': { category: 'Electrical', unit: 'pts', rate: 85.00, material: 'Copper' },
  'outlet': { category: 'Electrical', unit: 'pts', rate: 65.00, material: 'PVC' },
  'switch': { category: 'Electrical', unit: 'pts', rate: 45.00, material: 'Plastic' },
}

function computeQuantity(obj: any): number {
  if (obj.quantity_estimate) return obj.quantity_estimate

  const bbox = obj.bbox || {}
  const width = bbox.width || 0
  const height = bbox.height || 0

  // Compute based on type
  if (['wall', 'interior_wall', 'exterior_wall'].includes(obj.type)) {
    return Math.round(width * height * 100) / 100 // m2
  }
  if (obj.unit === 'pcs') return 1
  if (obj.unit === 'm') return Math.round(width * 100) / 100
  if (obj.unit === 'm2') return Math.round(width * height * 100) / 100

  return 1
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const body = await req.json()
    const { project_id, drawing_id, detected_objects } = body

    if (!project_id) {
      return new Response(
        JSON.stringify({ success: false, error: 'project_id required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    console.log(`[compute-quantities] Processing project ${project_id}`)

    // Get detected objects from DB if not provided
    let objects = detected_objects
    if (!objects || objects.length === 0) {
      const query = supabase
        .from('detected_objects')
        .select('*')
        .eq('project_id', project_id)
      
      if (drawing_id) {
        query.eq('drawing_id', drawing_id)
      }

      const { data: dbObjects, error: fetchError } = await query

      if (fetchError) throw fetchError
      objects = dbObjects || []
    }

    if (objects.length === 0) {
      return new Response(
        JSON.stringify({ success: false, error: 'No detected objects found' }),
        { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    console.log(`[compute-quantities] Processing ${objects.length} objects`)

    // Fetch BOQ rules from database
    const { data: dbRules } = await supabase
      .from('boq_rules')
      .select('*')
      .eq('active', true)

    const rules = dbRules || []

    // Compute BOQ items
    const boqItems: BOQItem[] = []

    for (const obj of objects) {
      const objType = obj.type?.toLowerCase() || obj.object_type?.toLowerCase() || ''
      const trade = obj.trade || DEFAULT_RULES[objType]?.category || 'General'

      // Find matching rule
      let matchedRule = rules.find((r: any) =>
        r.object_type === objType ||
        r.trade === trade ||
        (r.keywords && objType.includes(r.keywords))
      )

      const defaultRule = DEFAULT_RULES[objType] || DEFAULT_RULES['wall']

      const quantity = computeQuantity(obj)
      const rate = matchedRule?.rate || defaultRule.rate
      const material = obj.material_hint || matchedRule?.material || defaultRule.material
      const unit = obj.unit || matchedRule?.unit || defaultRule.unit
      const category = matchedRule?.category || defaultRule.category

      const boqItem: BOQItem = {
        project_id: parseInt(project_id),
        drawing_id: drawing_id ? parseInt(drawing_id) : undefined,
        trade,
        category,
        description: `${obj.label || objType} - ${material}`,
        material,
        unit,
        quantity,
        rate,
        amount: Math.round(quantity * rate * 100) / 100,
        detected_object_id: obj.id,
        rule_id: matchedRule?.id,
      }

      boqItems.push(boqItem)
    }

    // Insert BOQ items into database
    if (boqItems.length > 0) {
      const { error: insertError } = await supabase
        .from('boq_items')
        .insert(boqItems)

      if (insertError) {
        console.error('[compute-quantities] Insert error:', insertError)
        // Try individual inserts as fallback
        for (const item of boqItems) {
          await supabase.from('boq_items').insert(item)
        }
      }
    }

    // Group by trade for summary
    const tradeSummary = boqItems.reduce((acc: Record<string, any>, item) => {
      if (!acc[item.trade]) {
        acc[item.trade] = { trade: item.trade, items: 0, total_quantity: 0, total_amount: 0 }
      }
      acc[item.trade].items++
      acc[item.trade].total_quantity += item.quantity
      acc[item.trade].total_amount += item.amount
      return acc
    }, {})

    const grandTotal = boqItems.reduce((sum, item) => sum + item.amount, 0)

    return new Response(
      JSON.stringify({
        success: true,
        data: {
          boq_items: boqItems,
          trade_summary: Object.values(tradeSummary),
          grand_total: Math.round(grandTotal * 100) / 100,
          item_count: boqItems.length,
        },
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  } catch (error) {
    console.error('[compute-quantities] Error:', error)
    return new Response(
      JSON.stringify({ success: false, error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
