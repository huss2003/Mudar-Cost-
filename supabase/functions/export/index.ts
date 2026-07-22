import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const supabaseUrl = Deno.env.get('SUPABASE_URL')!
const supabaseKey = Deno.env.get('SUPABASE_ANON_KEY')!
const supabase = createClient(supabaseUrl, supabaseKey)

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

function generateCSV(boqItems: any[], project: any): string {
  const lines: string[] = []
  
  // Header
  lines.push('Bill of Quantities')
  lines.push(`Project: ${project?.name || 'N/A'}`)
  lines.push(`Date: ${new Date().toLocaleDateString()}`)
  lines.push('')
  
  // Column headers
  lines.push('Trade,Category,Description,Material,Quantity,Unit,Rate,Amount')
  
  // Items grouped by trade
  const grouped = boqItems.reduce((acc: Record<string, any[]>, item: any) => {
    const trade = item.trade || 'General'
    if (!acc[trade]) acc[trade] = []
    acc[trade].push(item)
    return acc
  }, {})

  let grandTotal = 0
  for (const [trade, items] of Object.entries(grouped)) {
    lines.push('')
    lines.push(`--- ${trade} ---`)
    let tradeTotal = 0
    
    for (const item of items) {
      const amount = (item.quantity * item.rate).toFixed(2)
      tradeTotal += parseFloat(amount)
      lines.push([
        trade,
        item.category || '',
        item.description || '',
        item.material || '',
        item.quantity,
        item.unit || '',
        item.rate?.toFixed(2) || '0.00',
        amount,
      ].join(','))
    }
    
    lines.push(`${trade} Subtotal,,,${tradeTotal.toFixed(2)}`)
    grandTotal += tradeTotal
  }
  
  lines.push('')
  lines.push(`Grand Total,,,,,,, ${grandTotal.toFixed(2)}`)
  
  return lines.join('\n')
}

function generateHTML(boqItems: any[], project: any, costSummary: any): string {
  const grouped = boqItems.reduce((acc: Record<string, any[]>, item: any) => {
    const trade = item.trade || 'General'
    if (!acc[trade]) acc[trade] = []
    acc[trade].push(item)
    return acc
  }, {})

  let tradeRows = ''
  let grandTotal = 0

  for (const [trade, items] of Object.entries(grouped)) {
    let tradeTotal = 0
    let itemRows = ''
    
    for (const item of items) {
      const amount = (item.quantity * item.rate).toFixed(2)
      tradeTotal += parseFloat(amount)
      itemRows += `
        <tr>
          <td>${item.description || ''}</td>
          <td>${item.material || ''}</td>
          <td class="num">${item.quantity}</td>
          <td>${item.unit || ''}</td>
          <td class="num">$${item.rate?.toFixed(2) || '0.00'}</td>
          <td class="num">$${amount}</td>
        </tr>`
    }
    
    tradeRows += `
      <tr class="trade-header">
        <td colspan="5"><strong>${trade}</strong></td>
        <td class="num"><strong>$${tradeTotal.toFixed(2)}</strong></td>
      </tr>
      ${itemRows}`
    
    grandTotal += tradeTotal
  }

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Bill of Quantities - ${project?.name || 'Project'}</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 40px; color: #333; }
    h1 { color: #1a365d; border-bottom: 2px solid #2b6cb0; padding-bottom: 10px; }
    h2 { color: #2c5282; margin-top: 30px; }
    .header { margin-bottom: 30px; }
    .header p { margin: 5px 0; color: #666; }
    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    th { background: #2b6cb0; color: white; padding: 12px 8px; text-align: left; }
    td { padding: 10px 8px; border-bottom: 1px solid #e2e8f0; }
    .num { text-align: right; font-family: monospace; }
    .trade-header { background: #ebf8ff; }
    .trade-header td { border-top: 2px solid #2b6cb0; }
    .summary { margin-top: 40px; padding: 20px; background: #f7fafc; border-radius: 8px; }
    .summary table { margin-top: 10px; }
    .summary td { padding: 8px; }
    .grand-total { font-size: 1.2em; font-weight: bold; color: #1a365d; }
    @media print {
      body { margin: 20px; }
      .no-print { display: none; }
    }
  </style>
</head>
<body>
  <div class="header">
    <h1>Bill of Quantities</h1>
    <p><strong>Project:</strong> ${project?.name || 'N/A'}</p>
    <p><strong>Date:</strong> ${new Date().toLocaleDateString()}</p>
    <p><strong>Reference:</strong> BOQ-${project?.id || '000'}-${Date.now()}</p>
  </div>

  <h2>Cost Breakdown by Trade</h2>
  <table>
    <thead>
      <tr>
        <th>Description</th>
        <th>Material</th>
        <th class="num">Quantity</th>
        <th>Unit</th>
        <th class="num">Rate</th>
        <th class="num">Amount</th>
      </tr>
    </thead>
    <tbody>
      ${tradeRows}
    </tbody>
  </table>

  <div class="summary">
    <h2>Cost Summary</h2>
    <table>
      <tr><td>Materials Total:</td><td class="num">$${costSummary?.materials_total?.toFixed(2) || grandTotal.toFixed(2)}</td></tr>
      <tr><td>Labour (35%):</td><td class="num">$${costSummary?.labour_total?.toFixed(2) || (grandTotal * 0.35).toFixed(2)}</td></tr>
      <tr><td>Equipment (8%):</td><td class="num">$${costSummary?.equipment_total?.toFixed(2) || (grandTotal * 0.08).toFixed(2)}</td></tr>
      <tr><td>Subtotal:</td><td class="num">$${costSummary?.subtotal?.toFixed(2) || (grandTotal * 1.43).toFixed(2)}</td></tr>
      <tr><td>Markup (${costSummary?.markup_pct || 15}%):</td><td class="num">$${costSummary?.markup_amount?.toFixed(2) || (grandTotal * 1.43 * 0.15).toFixed(2)}</td></tr>
      <tr><td>Contingency (${costSummary?.contingency_pct || 5}%):</td><td class="num">$${costSummary?.contingency_amount?.toFixed(2) || (grandTotal * 1.43 * 0.05).toFixed(2)}</td></tr>
      <tr class="grand-total">
        <td><strong>GRAND TOTAL:</strong></td>
        <td class="num"><strong>$${costSummary?.grand_total?.toFixed(2) || (grandTotal * 1.43 * 1.20).toFixed(2)}</strong></td>
      </tr>
    </table>
  </div>

  <div class="no-print" style="margin-top: 40px; text-align: center;">
    <button onclick="window.print()" style="padding: 12px 24px; font-size: 16px; background: #2b6cb0; color: white; border: none; border-radius: 6px; cursor: pointer;">
      Print / Save as PDF
    </button>
  </div>
</body>
</html>`
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const body = await req.json()
    const { project_id, export_type = 'xlsx' } = body

    if (!project_id) {
      return new Response(
        JSON.stringify({ success: false, error: 'project_id required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    console.log(`[export] Generating ${export_type} for project ${project_id}`)

    // Fetch project details
    const { data: project, error: projectError } = await supabase
      .from('projects')
      .select('*')
      .eq('id', project_id)
      .single()

    if (projectError || !project) {
      return new Response(
        JSON.stringify({ success: false, error: 'Project not found' }),
        { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // Fetch BOQ items
    const { data: boqItems, error: boqError } = await supabase
      .from('boq_items')
      .select('*')
      .eq('project_id', project_id)
      .order('trade')

    if (boqError) throw boqError

    if (!boqItems || boqItems.length === 0) {
      return new Response(
        JSON.stringify({ success: false, error: 'No BOQ items to export' }),
        { status: 404, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      )
    }

    // Fetch latest cost summary
    const { data: costVersion } = await supabase
      .from('cost_versions')
      .select('*')
      .eq('project_id', project_id)
      .order('created_at', { ascending: false })
      .limit(1)
      .single()

    let fileContent: string
    let contentType: string
    let fileExtension: string

    if (export_type === 'pdf') {
      fileContent = generateHTML(boqItems, project, costVersion)
      contentType = 'text/html'
      fileExtension = 'html'
    } else {
      // Default to CSV (Excel-compatible)
      fileContent = generateCSV(boqItems, project)
      contentType = 'text/csv'
      fileExtension = 'csv'
    }

    // Upload to Supabase Storage
    const fileName = `exports/${project_id}/boq-${Date.now()}.${fileExtension}`
    
    const { error: uploadError } = await supabase.storage
      .from('exports')
      .upload(fileName, fileContent, {
        contentType,
        upsert: true,
      })

    if (uploadError) {
      console.error('[export] Upload error:', uploadError)
      // Fallback: return content directly
      return new Response(fileContent, {
        headers: {
          ...corsHeaders,
          'Content-Type': contentType,
          'Content-Disposition': `attachment; filename="boq-${project_id}.${fileExtension}"`,
        },
      })
    }

    // Get public URL
    const { data: urlData } = supabase.storage
      .from('exports')
      .getPublicUrl(fileName)

    const fileUrl = urlData?.publicUrl || `${supabaseUrl}/storage/v1/object/public/exports/${fileName}`

    // Log export
    await supabase.from('cost_history').insert({
      project_id: parseInt(project_id),
      action: 'export',
      export_type,
      file_url: fileUrl,
      exported_at: new Date().toISOString(),
    })

    return new Response(
      JSON.stringify({
        success: true,
        data: {
          file_url: fileUrl,
          file_name: fileName,
          export_type,
          item_count: boqItems.length,
        },
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  } catch (error) {
    console.error('[export] Error:', error)
    return new Response(
      JSON.stringify({ success: false, error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    )
  }
})
