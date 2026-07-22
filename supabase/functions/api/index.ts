import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabaseUrl = Deno.env.get('SUPABASE_URL')!
const supabaseKey = Deno.env.get('SUPABASE_ANON_KEY')!
const supabase = createClient(supabaseUrl, supabaseKey)

// CORS headers
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })

  const url = new URL(req.url)
  const path = url.pathname.replace('/api/v1', '')

  try {
    // Health check
    if (path === '/healthz' || path === '/health') {
      return new Response(JSON.stringify({ status: 'alive' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      })
    }

    // Projects list
    if (path === '/projects' && req.method === 'GET') {
      const { data, error } = await supabase.from('projects').select('*').order('created_at', { ascending: false })
      if (error) throw error
      return new Response(JSON.stringify(data), { headers: { ...corsHeaders, 'Content-Type': 'application/json' } })
    }

    // Create project
    if (path === '/projects' && req.method === 'POST') {
      const body = await req.json()
      const { data, error } = await supabase.from('projects').insert(body).select().single()
      if (error) throw error
      return new Response(JSON.stringify(data), { 
        status: 201,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      })
    }

    // Get project
    const projectMatch = path.match(/^\/projects\/(\d+)$/)
    if (projectMatch && req.method === 'GET') {
      const { data, error } = await supabase.from('projects').select('*').eq('id', projectMatch[1]).single()
      if (error) throw error
      return new Response(JSON.stringify(data), { headers: { ...corsHeaders, 'Content-Type': 'application/json' } })
    }

    // Upload drawing (placeholder for file upload)
    if (path.match(/^\/projects\/(\d+)\/drawings$/) && req.method === 'POST') {
      return new Response(JSON.stringify({ message: 'Upload via Supabase Storage directly', status: 'ok' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      })
    }

    // 404
    return new Response(JSON.stringify({ error: 'Not found' }), {
      status: 404,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    })

  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    })
  }
})
