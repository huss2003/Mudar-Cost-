import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabaseUrl = Deno.env.get('SUPABASE_URL')!
const supabaseKey = Deno.env.get('SUPABASE_ANON_KEY')!
const supabase = createClient(supabaseUrl, supabaseKey)

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

interface CostBreakdown {
  trade: string
  category: string
  items: Array<{
    description: string
    material: string
    quantity: number
    unit: string
    rate: number
    amount: number
    vendor?: string
    variant?: string
  }>
  subtotal: number
  percentage: number
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const body = await req.json()
    const { project_id, boq_items, markup_pct = 15, contingency_pct = 5 } = body

    if (!project_id) {
      return new Response(
        JSON.stringify({ success: false, error: 'project_id required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    console.log(`[compute-costs] Processing project ${project_id}`)

    // Get BOQ items from DB if not provided
    let items = boq_items
    if (!items || items.length === 0) {
      const { data: dbItems, error: fetchError } = await supabase
        .from('boq_items')
        .select('*')
        .eq('project_id', project_id)

      if (fetchError) throw fetchError
      items = dbItems || []
    }

    if (items.length === 0) {
      return new Response(
        JSON.stringify({ success: false, error: 'No BOQ items found' }),
        { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    console.log(`[compute-costs] Processing ${items.length} BOQ items`)

    // Fetch material rates from database
    const { data: materials } = await supabase
      .from('materials')
      .select('*')

    const { data: vendors } = await supabase
      .from('vendors')
      .select('*')

    const { data: labourRates } = await supabase
      .from('labour_rates')
      .select('*')

    // Build rate lookup maps
    const materialRates: Record<string, any> = {}
    for (const m of materials || []) {
      materialRates[m.name?.toLowerCase()] = m
      if (m.category) materialRates[m.category.toLowerCase()] = m
    }

    const vendorMap: Record<string, any> = {}
    for (const v of vendors || []) {
      vendorMap[v.name?.toLowerCase()] = v
    }

    // Enrich items with material rates
    const enrichedItems = items.map((item: any) => {
      const matKey = item.material?.toLowerCase() || ''
      const material = materialRates[matKey]
      
      // Use material rate if available, otherwise use item rate
      const rate = material?.unit_price || item.rate || 0
      const vendor = material?.preferred_vendor || null
      const variant = material?.variant || null

      return {
        ...item,
        rate,
        amount: Math.round(item.quantity * rate * 100) / 100,
        vendor,
        variant,
      }
    })

    // Group by trade
    const tradeMap: Record<string, CostBreakdown> = {}
    for (const item of enrichedItems) {
      const trade = item.trade || 'General'
      if (!tradeMap[trade]) {
        tradeMap[trade] = {
          trade,
          category: item.category || 'General',
          items: [],
          subtotal: 0,
          percentage: 0,
        }
      }
      tradeMap[trade].items.push({
        description: item.description,
        material: item.material,
        quantity: item.quantity,
        unit: item.unit,
        rate: item.rate,
        amount: item.amount,
        vendor: item.vendor,
        variant: item.variant,
      })
      tradeMap[trade].subtotal += item.amount
    }

    // Calculate grand totals
    const materialsTotal = Object.values(tradeMap).reduce((sum, t) => sum + t.subtotal, 0)
    const labourTotal = materialsTotal * 0.35 // 35% labour estimate
    const equipmentTotal = materialsTotal * 0.08 // 8% equipment estimate
    const subtotal = materialsTotal + labourTotal + equipmentTotal
    const markup = Math.round(subtotal * markup_pct / 100 * 100) / 100
    const contingency = Math.round(subtotal * contingency_pct / 100 * 100) / 100
    const grandTotal = subtotal + markup + contingency

    // Calculate percentages
    for (const trade of Object.values(tradeMap)) {
      trade.percentage = materialsTotal > 0
        ? Math.round(trade.subtotal / materialsTotal * 10000) / 100
        : 0
      trade.subtotal = Math.round(trade.subtotal * 100) / 100
    }

    // Save cost version
    const costVersion = {
      project_id: parseInt(project_id),
      version_number: 1,
      status: 'draft',
      materials_total: Math.round(materialsTotal * 100) / 100,
      labour_total: Math.round(labourTotal * 100) / 100,
      equipment_total: Math.round(equipmentTotal * 100) / 100,
      subtotal: Math.round(subtotal * 100) / 100,
      markup_pct,
      markup_amount: markup,
      contingency_pct,
      contingency_amount: contingency,
      grand_total: Math.round(grandTotal * 100) / 100,
      breakdown: tradeMap,
    }

    const { data: versionData, error: versionError } = await supabase
      .from('cost_versions')
      .insert(costVersion)
      .select()
      .single()

    if (versionError) {
      console.error('[compute-costs] Version save error:', versionError)
    }

    // Update project costs
    await supabase
      .from('project_costs')
      .upsert({
        project_id: parseInt(project_id),
        estimated_cost: Math.round(grandTotal * 100) / 100,
        materials_cost: Math.round(materialsTotal * 100) / 100,
        labour_cost: Math.round(labourTotal * 100) / 100,
        equipment_cost: Math.round(equipmentTotal * 100) / 100,
        updated_at: new Date().toISOString(),
      })

    return new Response(
      JSON.stringify({
        success: true,
        data: {
          cost_version_id: versionData?.id,
          trade_breakdown: Object.values(tradeMap),
          summary: {
            materials_total: Math.round(materialsTotal * 100) / 100,
            labour_total: Math.round(labourTotal * 100) / 100,
            equipment_total: Math.round(equipmentTotal * 100) / 100,
            subtotal: Math.round(subtotal * 100) / 100,
            markup_pct,
            markup_amount: markup,
            contingency_pct,
            contingency_amount: contingency,
            grand_total: Math.round(grandTotal * 100) / 100,
          },
          item_count: enrichedItems.length,
        },
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  } catch (error) {
    console.error('[compute-costs] Error:', error)
    return new Response(
      JSON.stringify({ success: false, error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
