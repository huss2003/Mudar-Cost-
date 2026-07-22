import { useState, useCallback } from 'react';
import {
  Text,
  Badge,
  Card,
  Group,
  Stack,
  Title,
  Box,
  Grid,
  Button,
  Loader,
  Paper,
  Table,
} from '@mantine/core';
import {
  IconFileExport,
  IconDownload,
  IconFileSpreadsheet,
  IconFileText,
  IconClipboardList,
  IconCheck,
  IconFileInvoice,
  IconReceipt,
} from '@tabler/icons-react';
import supabase from '../api/supabase';

/* ─── Currency formatter ─────────────────────────────────────── */
const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value);

/* ─── Generate CSV content ───────────────────────────────────── */
function generateCSV(headers: string[], rows: string[][]): string {
  const escape = (val: string) => `"${val.replace(/"/g, '""')}"`;
  const headerLine = headers.map(escape).join(',');
  const dataLines = rows.map((row) => row.map(escape).join(',')).join('\n');
  return `${headerLine}\n${dataLines}`;
}

function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/* ════════════════════════════════════════════════════════════════ */
/*  EXPORT CARD                                                   */
/* ════════════════════════════════════════════════════════════════ */
function ExportCard({
  icon: Icon,
  title,
  description,
  color,
  onExport,
  loading,
}: {
  icon: typeof IconFileSpreadsheet;
  title: string;
  description: string;
  color: string;
  onExport: () => void;
  loading: boolean;
}) {
  return (
    <Card
      p="lg"
      className="ace-card ace-animate-in"
      style={{ cursor: 'pointer' }}
      onClick={onExport}
    >
      <Stack gap="md">
        <Group gap="sm">
          <Box
            style={{
              width: 44,
              height: 44,
              borderRadius: '12px',
              background: `${color}15`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Icon size={22} style={{ color }} />
          </Box>
          <div>
            <Text fw={600} size="sm">{title}</Text>
            <Text size="xs" c="dimmed">{description}</Text>
          </div>
        </Group>
        <Button
          variant="light"
          color="accent"
          size="sm"
          fullWidth
          leftSection={loading ? <Loader size={14} /> : <IconDownload size={14} />}
          loading={loading}
          onClick={(e) => { e.stopPropagation(); onExport(); }}
          className="ace-btn"
        >
          {loading ? 'Generating...' : `Export ${title}`}
        </Button>
      </Stack>
    </Card>
  );
}

/* ════════════════════════════════════════════════════════════════ */
/*  MAIN COMPONENT                                                */
/* ════════════════════════════════════════════════════════════════ */

export default function Exports() {
  const [loadingStates, setLoadingStates] = useState<Record<string, boolean>>({});
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const setLoading = (key: string, val: boolean) =>
    setLoadingStates((prev) => ({ ...prev, [key]: val }));

  const showSuccess = (msg: string) => {
    setSuccessMessage(msg);
    setTimeout(() => setSuccessMessage(null), 3000);
  };

  /* ── Export BOQ as CSV ────────────────────────────────────── */
  const exportBOQ = useCallback(async () => {
    setLoading('boq', true);
    try {
      const { data, error } = await supabase
        .from('boq_items')
        .select('description, quantity, unit, rate, total, trade');

      if (error) throw error;

      const items = (data as any[]) || [];
      const headers = ['Category', 'Description', 'Quantity', 'Unit', 'Rate (₹)', 'Total (₹)'];
      const rows = items.map((item) => [
        item.trade || 'General',
        item.description || '',
        String(item.quantity || 0),
        item.unit || 'nos',
        String(item.rate || 0),
        String(item.total || 0),
      ]);

      // Add total row
      const grandTotal = items.reduce((sum: number, item: any) => sum + (item.total || 0), 0);
      rows.push(['', '', '', '', 'Grand Total', String(grandTotal)]);

      const csv = generateCSV(headers, rows);
      downloadFile(csv, `AutoCost_BOQ_${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv');
      showSuccess('BOQ exported as CSV');
    } catch (err: unknown) {
      console.error('Export failed:', err);
    } finally {
      setLoading('boq', false);
    }
  }, []);

  /* ── Export Materials as CSV ──────────────────────────────── */
  const exportMaterials = useCallback(async () => {
    setLoading('materials', true);
    try {
      const { data, error } = await supabase
        .from('materials')
        .select('name, brand, sku, category, rate, unit, lead_time_days, warranty');

      if (error) throw error;

      const items = (data as any[]) || [];
      const headers = ['Name', 'Brand', 'SKU', 'Category', 'Rate (₹)', 'Unit', 'Lead Time (days)', 'Warranty'];
      const rows = items.map((item) => [
        item.name || '',
        item.brand || '',
        item.sku || '',
        item.category || '',
        String(item.rate || 0),
        item.unit || '',
        String(item.lead_time_days || 0),
        item.warranty || '',
      ]);

      const csv = generateCSV(headers, rows);
      downloadFile(csv, `AutoCost_Materials_${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv');
      showSuccess('Materials catalog exported as CSV');
    } catch (err: unknown) {
      console.error('Export failed:', err);
    } finally {
      setLoading('materials', false);
    }
  }, []);

  /* ── Export Purchase List ─────────────────────────────────── */
  const exportPurchaseList = useCallback(async () => {
    setLoading('purchase', true);
    try {
      const { data, error } = await supabase
        .from('boq_items')
        .select('description, quantity, unit, rate, total, material_name');

      if (error) throw error;

      const items = (data as any[]) || [];
      const headers = ['Material', 'Description', 'Quantity', 'Unit', 'Unit Rate (₹)', 'Total (₹)', 'Priority'];
      const rows = items
        .filter((item) => item.total > 0)
        .sort((a: any, b: any) => (b.total || 0) - (a.total || 0))
        .map((item) => [
          item.material_name || '',
          item.description || '',
          String(item.quantity || 0),
          item.unit || 'nos',
          String(item.rate || 0),
          String(item.total || 0),
          (item.total || 0) > 50000 ? 'High' : (item.total || 0) > 10000 ? 'Medium' : 'Low',
        ]);

      const csv = generateCSV(headers, rows);
      downloadFile(csv, `AutoCost_PurchaseList_${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv');
      showSuccess('Purchase list exported as CSV');
    } catch (err: unknown) {
      console.error('Export failed:', err);
    } finally {
      setLoading('purchase', false);
    }
  }, []);

  /* ── Export Summary Report ────────────────────────────────── */
  const exportSummary = useCallback(async () => {
    setLoading('summary', true);
    try {
      // Gather data from multiple tables
      const [boqResult, materialsResult, drawingsResult] = await Promise.all([
        supabase.from('boq_items').select('trade, total, quantity, rate'),
        supabase.from('materials').select('id'),
        supabase.from('drawings').select('id, name, status'),
      ]);

      const boqItems = (boqResult.data as any[]) || [];
      const materials = materialsResult.data || [];
      const drawings = (drawingsResult.data as any[]) || [];

      const grandTotal = boqItems.reduce((sum: number, item: any) => sum + (item.total || 0), 0);

      // Build summary text
      const lines = [
        '╔══════════════════════════════════════════════╗',
        '║     AUTOCOST ENGINE - PROJECT SUMMARY        ║',
        '╚══════════════════════════════════════════════╝',
        '',
        `Generated: ${new Date().toLocaleString()}`,
        '',
        '─── PROJECT OVERVIEW ───',
        `Total Cost: ${formatCurrency(grandTotal)}`,
        `BOQ Items: ${boqItems.length}`,
        `Materials: ${materials.length}`,
        `Drawings: ${drawings.length}`,
        '',
        '─── COST BY TRADE ───',
      ];

      // Trade breakdown
      const tradeMap = new Map<string, number>();
      for (const item of boqItems) {
        const trade = item.trade || 'General';
        tradeMap.set(trade, (tradeMap.get(trade) || 0) + (item.total || 0));
      }
      const sorted = Array.from(tradeMap.entries()).sort((a, b) => b[1] - a[1]);
      for (const [trade, total] of sorted) {
        lines.push(`  ${trade.padEnd(20)} ${formatCurrency(total).padStart(15)}  (${((total / grandTotal) * 100).toFixed(1)}%)`);
      }

      lines.push('', '─── DRAWINGS STATUS ───');
      for (const drawing of drawings) {
        lines.push(`  ${drawing.name.padEnd(30)} [${drawing.status}]`);
      }

      lines.push('', '═══════════════════════════════════════════════');
      lines.push('Generated by Auto Cost Engine');

      const content = lines.join('\n');
      downloadFile(content, `AutoCost_Summary_${new Date().toISOString().slice(0, 10)}.txt`, 'text/plain');
      showSuccess('Summary report exported');
    } catch (err: unknown) {
      console.error('Export failed:', err);
    } finally {
      setLoading('summary', false);
    }
  }, []);

  return (
    <Box p="lg" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* ══════ HEADER ══════ */}
      <Group justify="space-between" mb="lg" wrap="wrap" gap="sm" className="ace-animate-in">
        <div>
          <Group gap="xs" mb={4}>
            <Badge size="sm" variant="light" color="orange" leftSection={<IconFileExport size={12} />}>
              Module
            </Badge>
          </Group>
          <Title order={2} fw={700} style={{ letterSpacing: '-0.02em' }}>
            <span className="ace-gradient-text">Exports</span>
          </Title>
          <Text size="sm" c="dimmed" mt={2}>
            Generate and download project reports and documents
          </Text>
        </div>
      </Group>

      {/* ══════ SUCCESS NOTIFICATION ══════ */}
      {successMessage && (
        <Paper
          p="sm"
          px="md"
          mb="md"
          className="ace-animate-in"
          style={{
            background: 'rgba(45, 212, 168, 0.08)',
            border: '1px solid rgba(45, 212, 168, 0.2)',
          }}
        >
          <Group gap="xs">
            <IconCheck size={16} style={{ color: 'var(--ace-success)' }} />
            <Text size="sm" style={{ color: 'var(--ace-success)' }}>{successMessage}</Text>
          </Group>
        </Paper>
      )}

      {/* ══════ EXPORT CARDS ══════ */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        <Grid gutter="md">
          <Grid.Col span={{ base: 12, sm: 6, lg: 3 }}>
            <ExportCard
              icon={IconFileSpreadsheet}
              title="BOQ Spreadsheet"
              description="Full Bill of Quantities with rates and totals"
              color="#2dd4a8"
              onExport={exportBOQ}
              loading={!!loadingStates.boq}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6, lg: 3 }}>
            <ExportCard
              icon={IconFileInvoice}
              title="Materials Catalog"
              description="Complete material database with pricing"
              color="#5e6ad2"
              onExport={exportMaterials}
              loading={!!loadingStates.materials}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6, lg: 3 }}>
            <ExportCard
              icon={IconClipboardList}
              title="Purchase List"
              description="Prioritized procurement list sorted by cost"
              color="#f97316"
              onExport={exportPurchaseList}
              loading={!!loadingStates.purchase}
            />
          </Grid.Col>
          <Grid.Col span={{ base: 12, sm: 6, lg: 3 }}>
            <ExportCard
              icon={IconReceipt}
              title="Summary Report"
              description="Complete project overview with all metrics"
              color="#a78bfa"
              onExport={exportSummary}
              loading={!!loadingStates.summary}
            />
          </Grid.Col>
        </Grid>

        {/* ══════ PREVIEW SECTION ══════ */}
        <Paper p="md" mt="lg" className="ace-animate-in" style={{ animationDelay: '200ms' }}>
          <Group justify="space-between" mb="md">
            <Text fw={600} size="sm">Export Options</Text>
          </Group>
          <Table withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Format</Table.Th>
                <Table.Th>Contents</Table.Th>
                <Table.Th>Use Case</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              <Table.Tr>
                <Table.Td>
                  <Group gap="xs">
                    <IconFileSpreadsheet size={14} style={{ color: '#2dd4a8' }} />
                    <Text size="sm">CSV / Excel</Text>
                  </Group>
                </Table.Td>
                <Table.Td><Text size="sm" c="dimmed">BOQ items, materials, purchase list</Text></Table.Td>
                <Table.Td><Text size="sm" c="dimmed">Import into spreadsheets, share with team</Text></Table.Td>
              </Table.Tr>
              <Table.Tr>
                <Table.Td>
                  <Group gap="xs">
                    <IconFileText size={14} style={{ color: '#5e6ad2' }} />
                    <Text size="sm">Text Report</Text>
                  </Group>
                </Table.Td>
                <Table.Td><Text size="sm" c="dimmed">Project summary, cost breakdown</Text></Table.Td>
                <Table.Td><Text size="sm" c="dimmed">Quick reference, email attachment</Text></Table.Td>
              </Table.Tr>
            </Table.Tbody>
          </Table>
        </Paper>
      </div>
    </Box>
  );
}
