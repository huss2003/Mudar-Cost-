import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabaseUrl = Deno.env.get('SUPABASE_URL')!
const supabaseKey = Deno.env.get('SUPABASE_ANON_KEY')!
const supabase = createClient(supabaseUrl, supabaseKey)

const MIMO_API_KEY = Deno.env.get('MIMO_API_KEY') || 'sk-sj2opp4kpvdf8lg25py9mzjo1frd1w7uw65u1hquck807kx2'
const MIMO_ENDPOINT = 'https://api.xiaomimimo.com/v1/chat/completions'
const MIMO_MODEL = 'mimo-v2.5'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

interface DetectedObject {
  id: string
  type: string
  label: string
  confidence: number
  bbox: { x: number; y: number; width: number; height: number }
  trade?: string
  material_hint?: string
  quantity_estimate?: number
  unit?: string
}

async function detectObjects(imageUrl: string): Promise<DetectedObject[]> {
  const prompt = `You are an expert quantity surveyor and construction cost estimator. Analyze this floor plan image and detect all construction elements.

For each detected element, return a JSON array with:
- type: element type (wall, door, window, floor, ceiling, column, beam, pipe, fixture, electrical, etc.)
- label: descriptive label (e.g., "interior_wall", "exterior_wall", "sliding_door", "bathroom_tile")
- confidence: 0.0-1.0 confidence score
- bbox: bounding box {x, y, width, height} in normalized coordinates (0-1)
- trade: construction trade (masonry, carpentry, plumbing, electrical, tiling, painting, flooring, etc.)
- material_hint: suggested material (concrete, brick, timber, ceramic, etc.)
- quantity_estimate: estimated quantity based on visible dimensions
- unit: measurement unit (m, m2, m3, pcs, etc.)

Be thorough - detect ALL visible elements including:
- Walls (interior, exterior, partition)
- Doors (single, double, sliding, swing)
- Windows (casement, sliding, fixed)
- Flooring areas
- Ceiling areas  
- Fixtures (sinks, toilets, bathtubs, showers)
- Columns and beams
- Electrical outlets/switches
- Plumbing fixtures

Return ONLY the JSON array, no other text.`

  const response = await fetch(MIMO_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'api-key': MIMO_API_KEY,
    },
    body: JSON.stringify({
      model: MIMO_MODEL,
      messages: [
        {
          role: 'user',
          content: [
            { type: 'text', text: prompt },
            { type: 'image_url', image_url: { url: imageUrl } }
          ]
        }
      ],
      max_tokens: 4096,
      temperature: 0.1,
    }),
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`MiMo API error: ${response.status} - ${errorText}`)
  }

  const data = await response.json()
  const content = data.choices?.[0]?.message?.content || '[]'

  // Extract JSON from response (handle markdown code blocks)
  let jsonStr = content
  const jsonMatch = content.match(/```(?:json)?\s*([\s\S]*?)```/)
  if (jsonMatch) {
    jsonStr = jsonMatch[1]
  }
  // Also try to find array directly
  const arrayMatch = jsonStr.match(/\[[\s\S]*\]/)
  if (arrayMatch) {
    jsonStr = arrayMatch[0]
  }

  try {
    const objects = JSON.parse(jsonStr)
    return Array.isArray(objects) ? objects : []
  } catch {
    console.error('Failed to parse MiMo response:', content)
    return []
  }
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const body = await req.json()
    const { drawing_id, image_url, project_id } = body

    if (!image_url && !drawing_id) {
      return new Response(
        JSON.stringify({ success: false, error: 'image_url or drawing_id required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    let finalImageUrl = image_url

    // If drawing_id provided, fetch the image URL from drawings table
    if (drawing_id && !image_url) {
      const { data: drawing, error: drawError } = await supabase
        .from('drawings')
        .select('file_url, storage_path')
        .eq('id', drawing_id)
        .single()

      if (drawError || !drawing) {
        return new Response(
          JSON.stringify({ success: false, error: 'Drawing not found' }),
          { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        )
      }
      finalImageUrl = drawing.file_url || `${supabaseUrl}/storage/v1/object/public/drawings/${drawing.storage_path}`
    }

    console.log(`[detect] Starting detection for image: ${finalImageUrl}`)

    // Run AI detection
    const detectedObjects = await detectObjects(finalImageUrl)

    console.log(`[detect] Detected ${detectedObjects.length} objects`)

    // Store results in detected_objects table
    if (project_id && detectedObjects.length > 0) {
      const inserts = detectedObjects.map((obj, idx) => ({
        project_id: parseInt(project_id),
        drawing_id: drawing_id ? parseInt(drawing_id) : null,
        object_type: obj.type,
        label: obj.label,
        confidence: obj.confidence,
        bbox: obj.bbox,
        trade: obj.trade,
        material_hint: obj.material_hint,
        quantity_estimate: obj.quantity_estimate,
        unit: obj.unit,
        detection_model: MIMO_MODEL,
      }))

      const { error: insertError } = await supabase
        .from('detected_objects')
        .insert(inserts)

      if (insertError) {
        console.error('[detect] Insert error:', insertError)
      }

      // Update drawing status
      if (drawing_id) {
        await supabase
          .from('drawings')
          .update({ status: 'detected', detected_at: new Date().toISOString() })
          .eq('id', drawing_id)
      }
    }

    return new Response(
      JSON.stringify({
        success: true,
        data: {
          objects: detectedObjects,
          count: detectedObjects.length,
          image_url: finalImageUrl,
          model: MIMO_MODEL,
        },
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  } catch (error) {
    console.error('[detect] Error:', error)
    return new Response(
      JSON.stringify({ success: false, error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
