import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabaseUrl = Deno.env.get('SUPABASE_URL')!
const supabaseKey = Deno.env.get('SUPABASE_ANON_KEY')!
const supabase = createClient(supabaseUrl, supabaseKey)

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

// Function registry
const FUNCTIONS: Record<string, string> = {
  'detect': 'detect',
  'compute-quantities': 'compute-quantities',
  'compute-costs': 'compute-costs',
  'export': 'export',
}

// Health check
function healthCheck() {
  return {
    status: 'healthy',
    service: 'auto-cost-engine-api',
    version: '1.0.0',
    timestamp: new Date().toISOString(),
    functions: Object.keys(FUNCTIONS),
  }
}

// Projects CRUD
async function handleProjects(req: Request, path: string) {
  const method = req.method

  // List projects
  if (path === '/projects' && method === 'GET') {
    const { data, error } = await supabase
      .from('projects')
      .select('*')
      .order('created_at', { ascending: false })
    if (error) throw error
    return { success: true, data }
  }

  // Create project
  if (path === '/projects' && method === 'POST') {
    const body = await req.json()
    const { data, error } = await supabase
      .from('projects')
      .insert(body)
      .select()
      .single()
    if (error) throw error
    return { success: true, data }
  }

  // Get single project
  const projectMatch = path.match(/^\/projects\/(\d+)$/)
  if (projectMatch && method === 'GET') {
    const { data, error } = await supabase
      .from('projects')
      .select('*')
      .eq('id', projectMatch[1])
      .single()
    if (error) throw error
    return { success: true, data }
  }

  // Update project
  if (projectMatch && method === 'PATCH') {
    const body = await req.json()
    const { data, error } = await supabase
      .from('projects')
      .update(body)
      .eq('id', projectMatch[1])
      .select()
      .single()
    if (error) throw error
    return { success: true, data }
  }

  // Delete project
  if (projectMatch && method === 'DELETE') {
    const { error } = await supabase
      .from('projects')
      .delete()
      .eq('id', projectMatch[1])
    if (error) throw error
    return { success: true, data: { deleted: true } }
  }

  // Project drawings
  const drawingsMatch = path.match(/^\/projects\/(\d+)\/drawings$/)
  if (drawingsMatch && method === 'GET') {
    const { data, error } = await supabase
      .from('drawings')
      .select('*')
      .eq('project_id', drawingsMatch[1])
      .order('created_at', { ascending: false })
    if (error) throw error
    return { success: true, data }
  }

  // Project BOQ items
  const boqMatch = path.match(/^\/projects\/(\d+)\/boq$/)
  if (boqMatch && method === 'GET') {
    const { data, error } = await supabase
      .from('boq_items')
      .select('*')
      .eq('project_id', boqMatch[1])
      .order('trade')
    if (error) throw error
    return { success: true, data }
  }

  // Project costs
  const costsMatch = path.match(/^\/projects\/(\d+)\/costs$/)
  if (costsMatch && method === 'GET') {
    const { data, error } = await supabase
      .from('cost_versions')
      .select('*')
      .eq('project_id', costsMatch[1])
      .order('created_at', { ascending: false })
    if (error) throw error
    return { success: true, data }
  }

  return null
}

// Materials lookup
async function handleMaterials(req: Request, path: string) {
  if (path === '/materials' && req.method === 'GET') {
    const { data, error } = await supabase
      .from('materials')
      .select('*')
      .order('name')
    if (error) throw error
    return { success: true, data }
  }

  if (path === '/materials/search' && req.method === 'GET') {
    const url = new URL(req.url)
    const q = url.searchParams.get('q') || ''
    const { data, error } = await supabase
      .from('materials')
      .select('*')
      .ilike('name', `%${q}%`)
      .order('name')
    if (error) throw error
    return { success: true, data }
  }

  return null
}

// Vendors lookup
async function handleVendors(req: Request, path: string) {
  if (path === '/vendors' && req.method === 'GET') {
    const { data, error } = await supabase
      .from('vendors')
      .select('*')
      .order('name')
    if (error) throw error
    return { success: true, data }
  }

  return null
}

// AI Detection status
async function handleDetectionStatus(req: Request, path: string) {
  const statusMatch = path.match(/^\/projects\/(\d+)\/detection-status$/)
  if (statusMatch && req.method === 'GET') {
    const { data, error } = await supabase
      .from('detected_objects')
      .select('*')
      .eq('project_id', statusMatch[1])
    if (error) throw error

    const summary = {
      total_objects: data?.length || 0,
      by_type: (data || []).reduce((acc: Record<string, number>, obj: any) => {
        const type = obj.object_type || obj.type || 'unknown'
        acc[type] = (acc[type] || 0) + 1
        return acc
      }, {}),
      by_trade: (data || []).reduce((acc: Record<string, number>, obj: any) => {
        const trade = obj.trade || 'General'
        acc[trade] = (acc[trade] || 0) + 1
        return acc
      }, {}),
      average_confidence: data?.length
        ? data.reduce((sum: number, obj: any) => sum + (obj.confidence || 0), 0) / data.length
        : 0,
    }

    return { success: true, data: summary }
  }

  return null
}

serve(async (req) => {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  const url = new URL(req.url)
  const path = url.pathname.replace(/^\/api\/v1/, '').replace(/^\/functions\/v1/, '')

  console.log(`[router] ${req.method} ${path}`)

  try {
    // Health check
    if (path === '/health' || path === '/healthz' || path === '/') {
      return new Response(
        JSON.stringify({ success: true, data: healthCheck() }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // Projects routes
    const projectResult = await handleProjects(req, path)
    if (projectResult) {
      return new Response(
        JSON.stringify(projectResult),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // Materials routes
    const materialsResult = await handleMaterials(req, path)
    if (materialsResult) {
      return new Response(
        JSON.stringify(materialsResult),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // Vendors routes
    const vendorsResult = await handleVendors(req, path)
    if (vendorsResult) {
      return new Response(
        JSON.stringify(vendorsResult),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // Detection status
    const detectionResult = await handleDetectionStatus(req, path)
    if (detectionResult) {
      return new Response(
        JSON.stringify(detectionResult),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // Direct function invocation (for edge function deployment)
    for (const [funcName, funcPath] of Object.entries(FUNCTIONS)) {
      if (path.startsWith(`/${funcName}`) || path.startsWith(`/${funcPath}`)) {
        // Forward to the respective edge function
        const funcUrl = `${supabaseUrl}/functions/v1/${funcPath}`
        const forwardHeaders: Record<string, string> = {
          'Content-Type': 'application/json',
          'apikey': supabaseKey,
        }
        
        const authHeader = req.headers.get('authorization')
        if (authHeader) {
          forwardHeaders['authorization'] = authHeader
        }

        const forwardBody = req.method !== 'GET' ? await req.text() : undefined

        const funcResponse = await fetch(funcUrl, {
          method: req.method,
          headers: forwardHeaders,
          body: forwardBody,
        })

        const funcData = await funcResponse.json()
        return new Response(
          JSON.stringify(funcData),
          {
            status: funcResponse.status,
            headers: { ...corsHeaders, 'Content-Type': 'application/json' },
          }
        )
      }
    }

    // 404
    return new Response(
      JSON.stringify({
        success: false,
        error: 'Not found',
        available_routes: [
          'GET /health',
          'GET /projects',
          'POST /projects',
          'GET /projects/:id',
          'PATCH /projects/:id',
          'DELETE /projects/:id',
          'GET /projects/:id/drawings',
          'GET /projects/:id/boq',
          'GET /projects/:id/costs',
          'GET /projects/:id/detection-status',
          'GET /materials',
          'GET /materials/search?q=',
          'GET /vendors',
          'POST /detect',
          'POST /compute-quantities',
          'POST /compute-costs',
          'POST /export',
        ],
      }),
      { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  } catch (error) {
    console.error('[router] Error:', error)
    return new Response(
      JSON.stringify({ success: false, error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
