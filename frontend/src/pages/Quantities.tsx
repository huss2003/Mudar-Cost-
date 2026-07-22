import { useState, useMemo, useEffect, useCallback } from 'react';
import {
  Text,
  Badge,
  Paper,
  Grid,
  Group,
  Stack,
  Table,
  SegmentedControl,
  Title,
  Box,
  Loader,
  Alert,
} from '@mantine/core';
import {
  IconBox,
  IconLayoutBoard,
  IconInfoCircle,
  IconAlertCircle,
  IconCurrencyDollar,
} from '@tabler/icons-react';
import ThreeViewer from '../components/ThreeViewer';
import FinishPresetSelector from '../components/FinishPresetSelector';
import type { DetectedObject, FinishPreset } from '../types';
import supabase from '../api/supabase';

/* ─── Types ──────────────────────────────────────────────────── */
interface BoqItemRow {
  id: number;
  category: string;
  description: string;
  quantity: number;
  unit: string;
  rate: number;
  total: number;
}

/* ─── Currency formatter ─────────────────────────────────────── */
const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value);

/* ─── BOQ Table Component ────────────────────────────────────── */
function BoqTable({ items, loading, error }: { items: BoqItemRow[]; loading: boolean; error: string | null }) {
  const grandTotal = useMemo(
    () => items.reduce((sum, item) => sum + item.total, 0),
    [items]
  );

  if (loading) {
    return (
      <Group justify="center" py="xl">
        <Loader size="sm" />
        <Text size="sm" c="dimmed">Loading BOQ data...</Text>
      </Group>
    );
  }

  if (error) {
    return (
      <Alert icon={<IconAlertCircle size={16} />} color="red" p="xs">
        <Text size="xs">{error}</Text>
      </Alert>
    );
  }

  if (items.length === 0) {
    return (
      <Stack align="center" py="xl" gap="xs">
        <IconCurrencyDollar size={32} style={{ opacity: 0.15 }} />
        <Text size="sm" c="dimmed">No BOQ items found</Text>
        <Text size="xs" c="dimmed">Upload a drawing to generate quantities</Text>
      </Stack>
    );
  }

  return (
    <Table striped highlightOnHover withTableBorder>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Category</Table.Th>
          <Table.Th>Description</Table.Th>
          <Table.Th ta="right">Qty</Table.Th>
          <Table.Th>Unit</Table.Th>
          <Table.Th ta="right">Rate</Table.Th>
          <Table.Th ta="right">Total</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {items.map((item, idx) => (
          <Table.Tr key={item.id || idx}>
            <Table.Td>
              <Badge variant="light" size="sm" color="accent">
                {item.category}
              </Badge>
            </Table.Td>
            <Table.Td>
              <Text size="sm">{item.description}</Text>
            </Table.Td>
            <Table.Td ta="right">
              <Text size="sm" fw={500}>{item.quantity.toFixed(1)}</Text>
            </Table.Td>
            <Table.Td>
              <Text size="sm" c="dimmed">{item.unit}</Text>
            </Table.Td>
            <Table.Td ta="right">
              <Text size="sm">{formatCurrency(item.rate)}</Text>
            </Table.Td>
            <Table.Td ta="right">
              <Text size="sm" fw={600} style={{ color: 'var(--ace-success)' }}>
                {formatCurrency(item.total)}
              </Text>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
      <Table.Tfoot>
        <Table.Tr style={{ background: 'rgba(94,106,210,0.05)' }}>
          <Table.Th colSpan={5} ta="right">
            <Text fw={700} size="sm">Grand Total</Text>
          </Table.Th>
          <Table.Th ta="right">
            <Text fw={700} size="sm" className="ace-gradient-text">
              {formatCurrency(grandTotal)}
            </Text>
          </Table.Th>
        </Table.Tr>
      </Table.Tfoot>
    </Table>
  );
}

/* ─── Statistics Card ────────────────────────────────────────── */
function StatCard({ label, value, color, icon }: { label: string; value: string; color: string; icon: React.ReactNode }) {
  return (
    <Paper p="md" style={{ flex: 1 }}>
      <Group gap="sm">
        <Box
          style={{
            width: 40,
            height: 40,
            borderRadius: '10px',
            background: `${color}15`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {icon}
        </Box>
        <div>
          <Text size="xs" c="dimmed" fw={500}>{label}</Text>
          <Text size="lg" fw={700}>{value}</Text>
        </div>
      </Group>
    </Paper>
  );
}

/* ════════════════════════════════════════════════════════════════ */
/*  MAIN COMPONENT                                                */
/* ════════════════════════════════════════════════════════════════ */

export default function Quantities() {
  const [viewMode, setViewMode] = useState<'3d' | '2d'>('3d');
  const [finishPreset, setFinishPreset] = useState<FinishPreset>('modern');

  /* ── State for real data ─────────────────────────────────── */
  const [detectedObjects, setDetectedObjects] = useState<DetectedObject[]>([]);
  const [boqItems, setBoqItems] = useState<BoqItemRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* ── Fetch data from Supabase ────────────────────────────── */
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch detected objects
      const { data: objectsData, error: objError } = await supabase
        .from('detected_objects')
        .select('*')
        .order('id');

      if (objError) throw objError;

      // Fetch BOQ items
      const { data: boqData, error: boqError } = await supabase
        .from('boq_items')
        .select('*')
        .order('id');

      if (boqError) throw boqError;

      setDetectedObjects((objectsData as DetectedObject[]) || []);

      // Transform BOQ data - compute total if not present
      const transformedBoq = ((boqData as any[]) || []).map((item) => ({
        id: item.id,
        category: item.trade || item.category || 'General',
        description: item.description || '',
        quantity: item.quantity || 0,
        unit: item.unit || 'nos',
        rate: item.rate || 0,
        total: item.total || (item.quantity || 0) * (item.rate || 0),
      }));

      setBoqItems(transformedBoq);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load data';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  /* ── Computed stats ──────────────────────────────────────── */
  const grandTotal = useMemo(
    () => boqItems.reduce((sum, item) => sum + item.total, 0),
    [boqItems]
  );

  const objectCount = detectedObjects.length;

  return (
    <Box p="lg" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* ══════ HEADER ══════ */}
      <Group justify="space-between" mb="lg" wrap="wrap" gap="sm" className="ace-animate-in">
        <div>
          <Group gap="xs" mb={4}>
            <Badge size="sm" variant="light" color="cyan" leftSection={<IconBox size={12} />}>
              Module
            </Badge>
          </Group>
          <Title order={2} fw={700} style={{ letterSpacing: '-0.02em' }}>
            <span className="ace-gradient-text">Quantities</span>
          </Title>
          <Text size="sm" c="dimmed" mt={2}>
            Review quantity takeoffs and visualize in 3D
          </Text>
        </div>
        <Group gap="sm">
          <SegmentedControl
            value={viewMode}
            onChange={(val) => setViewMode(val as '3d' | '2d')}
            data={[
              {
                value: '3d',
                label: (
                  <Group gap={4} wrap="nowrap">
                    <IconBox size={14} />
                    <Text size="sm">3D View</Text>
                  </Group>
                ),
              },
              {
                value: '2d',
                label: (
                  <Group gap={4} wrap="nowrap">
                    <IconLayoutBoard size={14} />
                    <Text size="sm">Table</Text>
                  </Group>
                ),
              },
            ]}
            size="sm"
          />
        </Group>
      </Group>

      {/* ══════ STATS ══════ */}
      <Group gap="md" mb="lg" className="ace-animate-in" style={{ animationDelay: '100ms' }}>
        <StatCard
          label="Objects Detected"
          value={String(objectCount)}
          color="#a78bfa"
          icon={<IconBox size={20} style={{ color: '#a78bfa' }} />}
        />
        <StatCard
          label="BOQ Items"
          value={String(boqItems.length)}
          color="#38bdf8"
          icon={<IconLayoutBoard size={20} style={{ color: '#38bdf8' }} />}
        />
        <StatCard
          label="Project Total"
          value={formatCurrency(grandTotal)}
          color="#2dd4a8"
          icon={<IconCurrencyDollar size={20} style={{ color: '#2dd4a8' }} />}
        />
      </Group>

      {/* ══════ FINISH PRESET ══════ */}
      {viewMode === '3d' && (
        <Paper p="sm" mb="lg" className="ace-animate-in" style={{ animationDelay: '150ms' }}>
          <Group justify="space-between" align="center">
            <Group gap="xs">
              <IconInfoCircle size={16} style={{ color: 'var(--ace-text-tertiary)' }} />
              <Text size="sm" c="dimmed">Finish Preset</Text>
            </Group>
            <div style={{ flex: 1, maxWidth: 500 }}>
              <FinishPresetSelector value={finishPreset} onChange={setFinishPreset} />
            </div>
          </Group>
        </Paper>
      )}

      {/* ══════ CONTENT ══════ */}
      <div style={{ flex: 1, minHeight: 0 }}>
        {loading ? (
          <Paper
            p="xl"
            style={{
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Stack align="center" gap="md">
              <Loader size="lg" color="accent" />
              <Text size="sm" c="dimmed">Loading project data...</Text>
            </Stack>
          </Paper>
        ) : error ? (
          <Paper
            p="xl"
            style={{
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Stack align="center" gap="sm">
              <IconAlertCircle size={32} style={{ color: 'var(--ace-danger)' }} />
              <Text size="sm" style={{ color: 'var(--ace-danger)' }}>{error}</Text>
              <Text size="xs" c="dimmed">Check your connection and try again</Text>
            </Stack>
          </Paper>
        ) : viewMode === '3d' ? (
          <Grid gutter="md" style={{ height: '100%' }}>
            <Grid.Col span={{ base: 12, md: 7 }} style={{ height: '100%' }}>
              <Paper p={0} style={{ overflow: 'hidden', height: '100%' }}>
                <div style={{ height: '100%', minHeight: 480 }}>
                  <ThreeViewer
                    objects={detectedObjects}
                    finishPreset={finishPreset}
                    onObjectClick={(obj) => console.log('Object clicked:', obj)}
                  />
                </div>
              </Paper>
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 5 }} style={{ height: '100%' }}>
              <Paper p="md" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <Stack gap="sm" style={{ flex: 1 }}>
                  <Group justify="space-between">
                    <Text fw={600} size="sm">Bill of Quantities</Text>
                    <Badge size="sm" color="green" variant="light">
                      {boqItems.length} items
                    </Badge>
                  </Group>
                  <div style={{ flex: 1, overflowY: 'auto' }}>
                    <BoqTable items={boqItems} loading={false} error={null} />
                  </div>
                </Stack>
              </Paper>
            </Grid.Col>
          </Grid>
        ) : (
          <Paper p="md" style={{ height: '100%' }}>
            <Stack gap="sm">
              <Group justify="space-between">
                <Text fw={600} size="sm">Bill of Quantities</Text>
                <Badge size="sm" color="green" variant="light">
                  {boqItems.length} items
                </Badge>
              </Group>
              <div style={{ overflowY: 'auto', flex: 1 }}>
                <BoqTable items={boqItems} loading={false} error={null} />
              </div>
            </Stack>
          </Paper>
        )}
      </div>

      {/* ══════ FOOTER INFO ══════ */}
      {objectCount > 0 && (
        <Paper p="sm" mt="md" className="ace-animate-in" style={{ animationDelay: '200ms' }}>
          <Group gap="xs">
            <IconInfoCircle size={14} style={{ color: 'var(--ace-text-tertiary)' }} />
            <Text size="xs" c="dimmed">
              {objectCount} detected objects · Click any object in the 3D scene to inspect details
            </Text>
          </Group>
        </Paper>
      )}
    </Box>
  );
}
