import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Text,
  Badge,
  Card,
  Group,
  Stack,
  Title,
  Box,
  Grid,
  Loader,
  ActionIcon,
  Tooltip,
  Paper,
  Table,
} from '@mantine/core';
import {
  IconCurrencyDollar,
  IconAlertCircle,
  IconRefresh,
  IconTrendingUp,
  IconTrendingDown,
  IconChartPie,
  IconReceipt,
  IconCoin,
  IconStack,
} from '@tabler/icons-react';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import supabase from '../api/supabase';

/* ─── Types ──────────────────────────────────────────────────── */
interface CostBreakdown {
  trade: string;
  total: number;
  count: number;
}

interface CostVersion {
  id: number;
  project_id: number;
  version: number;
  total: number;
  created_at: string;
}

/* ─── Chart colors ───────────────────────────────────────────── */
const CHART_COLORS = [
  '#5e6ad2', '#2dd4a8', '#f97316', '#38bdf8', '#a78bfa',
  '#fb923c', '#e879f9', '#22d3ee', '#fbbf24', '#94a3b8',
];

/* ─── Currency formatter ─────────────────────────────────────── */
const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value);

const formatCompact = (value: number) => {
  if (value >= 10000000) return `₹${(value / 10000000).toFixed(1)}Cr`;
  if (value >= 100000) return `₹${(value / 100000).toFixed(1)}L`;
  if (value >= 1000) return `₹${(value / 1000).toFixed(1)}K`;
  return formatCurrency(value);
};

/* ─── Custom tooltip for Recharts ────────────────────────────── */
function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const data = payload[0].payload;
  return (
    <Box
      p="sm"
      style={{
        background: 'var(--ace-bg-surface)',
        border: '1px solid var(--ace-border)',
        borderRadius: '10px',
        boxShadow: 'var(--shadow-lg)',
      }}
    >
      <Text size="xs" fw={600}>{data.trade || data.name}</Text>
      <Text size="xs" c="dimmed">{formatCurrency(data.total)}</Text>
    </Box>
  );
}

/* ════════════════════════════════════════════════════════════════ */
/*  STAT CARD                                                     */
/* ════════════════════════════════════════════════════════════════ */
function StatCard({
  label, value, change, icon, color,
}: {
  label: string;
  value: string;
  change?: string;
  icon: React.ReactNode;
  color: string;
}) {
  return (
    <Paper p="md" style={{ flex: 1 }}>
      <Group justify="space-between" align="flex-start">
        <div>
          <Text size="xs" c="dimmed" fw={500}>{label}</Text>
          <Text size="xl" fw={700} mt={4}>{value}</Text>
          {change && (
            <Group gap={4} mt={4}>
              {change.startsWith('+') ? (
                <IconTrendingUp size={12} style={{ color: 'var(--ace-danger)' }} />
              ) : (
                <IconTrendingDown size={12} style={{ color: 'var(--ace-success)' }} />
              )}
              <Text size="xs" c={change.startsWith('+') ? 'red' : 'green'}>
                {change}
              </Text>
            </Group>
          )}
        </div>
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
      </Group>
    </Paper>
  );
}

/* ════════════════════════════════════════════════════════════════ */
/*  MAIN COMPONENT                                                */
/* ════════════════════════════════════════════════════════════════ */

export default function Costs() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [costBreakdown, setCostBreakdown] = useState<CostBreakdown[]>([]);
  const [costVersions, setCostVersions] = useState<CostVersion[]>([]);
  const [totalCost, setTotalCost] = useState(0);
  const [itemCount, setItemCount] = useState(0);

  /* ── Fetch cost data ─────────────────────────────────────── */
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch BOQ items for breakdown
      const { data: boqData, error: boqError } = await supabase
        .from('boq_items')
        .select('trade, total, id');

      if (boqError) throw boqError;

      // Fetch cost versions
      const { data: versionsData, error: versionsError } = await supabase
        .from('cost_versions')
        .select('*')
        .order('created_at', { ascending: false });

      if (versionsError) {
        console.warn('cost_versions table may not exist:', versionsError.message);
      }

      const items = (boqData as any[]) || [];

      // Compute breakdown by trade
      const tradeMap = new Map<string, { total: number; count: number }>();
      let grandTotal = 0;

      for (const item of items) {
        const trade = item.trade || 'General';
        const amount = item.total || 0;
        grandTotal += amount;

        const existing = tradeMap.get(trade) || { total: 0, count: 0 };
        tradeMap.set(trade, {
          total: existing.total + amount,
          count: existing.count + 1,
        });
      }

      const breakdown: CostBreakdown[] = Array.from(tradeMap.entries())
        .map(([trade, data]) => ({ trade, ...data }))
        .sort((a, b) => b.total - a.total);

      setCostBreakdown(breakdown);
      setCostVersions((versionsData as CostVersion[]) || []);
      setTotalCost(grandTotal);
      setItemCount(items.length);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load cost data';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  /* ── Computed data ────────────────────────────────────────── */
  const chartData = useMemo(
    () => costBreakdown.map((c) => ({ ...c, name: c.trade })),
    [costBreakdown]
  );

  const topTrade = costBreakdown.length > 0 ? costBreakdown[0] : null;
  const avgCostPerItem = itemCount > 0 ? totalCost / itemCount : 0;

  return (
    <Box p="lg" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* ══════ HEADER ══════ */}
      <Group justify="space-between" mb="lg" wrap="wrap" gap="sm" className="ace-animate-in">
        <div>
          <Group gap="xs" mb={4}>
            <Badge size="sm" variant="light" color="green" leftSection={<IconCurrencyDollar size={12} />}>
              Module
            </Badge>
          </Group>
          <Title order={2} fw={700} style={{ letterSpacing: '-0.02em' }}>
            <span className="ace-gradient-text">Cost Analysis</span>
          </Title>
          <Text size="sm" c="dimmed" mt={2}>
            Breakdown by trade and cost trends
          </Text>
        </div>
        <Tooltip label="Refresh">
          <ActionIcon variant="subtle" size="lg" onClick={fetchData} loading={loading}>
            <IconRefresh size={18} />
          </ActionIcon>
        </Tooltip>
      </Group>

      {/* ══════ STATS ══════ */}
      {!loading && !error && (
        <Group gap="md" mb="lg" className="ace-animate-in" style={{ animationDelay: '100ms' }}>
          <StatCard
            label="Total Project Cost"
            value={formatCurrency(totalCost)}
            icon={<IconCoin size={20} style={{ color: '#2dd4a8' }} />}
            color="#2dd4a8"
          />
          <StatCard
            label="Cost Items"
            value={String(itemCount)}
            icon={<IconReceipt size={20} style={{ color: '#5e6ad2' }} />}
            color="#5e6ad2"
          />
          <StatCard
            label="Avg per Item"
            value={formatCurrency(avgCostPerItem)}
            icon={<IconStack size={20} style={{ color: '#a78bfa' }} />}
            color="#a78bfa"
          />
          {topTrade && (
            <StatCard
              label="Largest Trade"
              value={topTrade.trade}
              change={`${formatCompact(topTrade.total)} (${((topTrade.total / totalCost) * 100).toFixed(0)}%)`}
              icon={<IconChartPie size={20} style={{ color: '#f97316' }} />}
              color="#f97316"
            />
          )}
        </Group>
      )}

      {/* ══════ CONTENT ══════ */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        {loading ? (
          <Paper p="xl" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Stack align="center" gap="md">
              <Loader size="lg" color="accent" />
              <Text size="sm" c="dimmed">Loading cost analysis...</Text>
            </Stack>
          </Paper>
        ) : error ? (
          <Paper p="xl" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Stack align="center" gap="sm">
              <IconAlertCircle size={32} style={{ color: 'var(--ace-danger)' }} />
              <Text size="sm" style={{ color: 'var(--ace-danger)' }}>{error}</Text>
              <ActionIcon variant="subtle" onClick={fetchData}><IconRefresh size={16} /></ActionIcon>
            </Stack>
          </Paper>
        ) : costBreakdown.length === 0 ? (
          <Paper p="xl" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Stack align="center" gap="xs">
              <IconCurrencyDollar size={40} style={{ opacity: 0.1 }} />
              <Text size="sm" c="dimmed">No cost data available</Text>
              <Text size="xs" c="dimmed">Add BOQ items to see cost breakdown</Text>
            </Stack>
          </Paper>
        ) : (
          <Grid gutter="md">
            {/* ── Pie chart ──────────────────────────────── */}
            <Grid.Col span={{ base: 12, md: 6 }}>
              <Paper p="md" h="100%">
                <Group justify="space-between" mb="md">
                  <Text fw={600} size="sm">Cost Distribution</Text>
                  <Badge size="xs" color="accent" variant="light">{costBreakdown.length} trades</Badge>
                </Group>
                <div style={{ height: 300 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={chartData}
                        cx="50%"
                        cy="50%"
                        innerRadius={70}
                        outerRadius={110}
                        paddingAngle={2}
                        dataKey="total"
                        nameKey="trade"
                        stroke="none"
                      >
                        {chartData.map((_, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={CHART_COLORS[index % CHART_COLORS.length]}
                            style={{ transition: 'all 0.2s ease' }}
                          />
                        ))}
                      </Pie>
                      <RechartsTooltip content={<CustomTooltip />} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                {/* Legend */}
                <Group gap="sm" mt="sm" justify="center" wrap="wrap">
                  {chartData.map((item, idx) => (
                    <Group key={item.trade} gap={4}>
                      <Box
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: '2px',
                          background: CHART_COLORS[idx % CHART_COLORS.length],
                        }}
                      />
                      <Text size="xs" c="dimmed">{item.trade}</Text>
                    </Group>
                  ))}
                </Group>
              </Paper>
            </Grid.Col>

            {/* ── Bar chart ──────────────────────────────── */}
            <Grid.Col span={{ base: 12, md: 6 }}>
              <Paper p="md" h="100%">
                <Group justify="space-between" mb="md">
                  <Text fw={600} size="sm">Cost by Trade</Text>
                </Group>
                <div style={{ height: 300 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} layout="vertical" margin={{ left: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                      <XAxis type="number" tick={{ fill: '#5c5e68', fontSize: 11 }} tickFormatter={(v) => formatCompact(v)} />
                      <YAxis type="category" dataKey="trade" tick={{ fill: '#8b8d97', fontSize: 11 }} width={80} />
                      <RechartsTooltip content={<CustomTooltip />} />
                      <Bar dataKey="total" radius={[0, 6, 6, 0]} barSize={24}>
                        {chartData.map((_, index) => (
                          <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Paper>
            </Grid.Col>

            {/* ── Breakdown table ────────────────────────── */}
            <Grid.Col span={{ base: 12, md: 8 }}>
              <Paper p="md">
                <Text fw={600} size="sm" mb="md">Detailed Breakdown</Text>
                <Table withTableBorder>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Trade</Table.Th>
                      <Table.Th ta="right">Items</Table.Th>
                      <Table.Th ta="right">Total</Table.Th>
                      <Table.Th ta="right">Share</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {costBreakdown.map((item, idx) => (
                      <Table.Tr key={item.trade}>
                        <Table.Td>
                          <Group gap="xs">
                            <Box
                              style={{
                                width: 8,
                                height: 8,
                                borderRadius: '2px',
                                background: CHART_COLORS[idx % CHART_COLORS.length],
                              }}
                            />
                            <Text size="sm" fw={500}>{item.trade}</Text>
                          </Group>
                        </Table.Td>
                        <Table.Td ta="right">
                          <Text size="sm" c="dimmed">{item.count}</Text>
                        </Table.Td>
                        <Table.Td ta="right">
                          <Text size="sm" fw={600}>{formatCurrency(item.total)}</Text>
                        </Table.Td>
                        <Table.Td ta="right">
                          <Text size="sm" c="dimmed">
                            {((item.total / totalCost) * 100).toFixed(1)}%
                          </Text>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                  <Table.Tfoot>
                    <Table.Tr style={{ background: 'rgba(94,106,210,0.05)' }}>
                      <Table.Th>Total</Table.Th>
                      <Table.Th ta="right">{itemCount}</Table.Th>
                      <Table.Th ta="right">
                        <Text fw={700} className="ace-gradient-text">
                          {formatCurrency(totalCost)}
                        </Text>
                      </Table.Th>
                      <Table.Th ta="right">100%</Table.Th>
                    </Table.Tr>
                  </Table.Tfoot>
                </Table>
              </Paper>
            </Grid.Col>

            {/* ── Version history ────────────────────────── */}
            <Grid.Col span={{ base: 12, md: 4 }}>
              <Paper p="md" style={{ height: '100%' }}>
                <Text fw={600} size="sm" mb="md">Version History</Text>
                {costVersions.length === 0 ? (
                  <Stack align="center" py="xl" gap="xs">
                    <IconTrendingUp size={24} style={{ opacity: 0.15 }} />
                    <Text size="xs" c="dimmed" ta="center">No version history yet</Text>
                  </Stack>
                ) : (
                  <Stack gap="xs">
                    {costVersions.map((v) => (
                      <Card key={v.id} p="xs">
                        <Group justify="space-between">
                          <div>
                            <Text size="xs" fw={600}>v{v.version}</Text>
                            <Text size="xs" c="dimmed">
                              {new Date(v.created_at).toLocaleDateString()}
                            </Text>
                          </div>
                          <Text size="xs" fw={600} style={{ color: 'var(--ace-success)' }}>
                            {formatCurrency(v.total)}
                          </Text>
                        </Group>
                      </Card>
                    ))}
                  </Stack>
                )}
              </Paper>
            </Grid.Col>
          </Grid>
        )}
      </div>
    </Box>
  );
}
