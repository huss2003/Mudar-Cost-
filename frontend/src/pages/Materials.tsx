import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Text,
  Badge,
  Card,
  Group,
  Stack,
  Title,
  Box,
  TextInput,
  Grid,
  Loader,
  Button,
  Tooltip,
  ActionIcon,
  Modal,
  Divider,
  Paper,
} from '@mantine/core';
import {
  IconBuildingStore,
  IconSearch,
  IconAlertCircle,
  IconRefresh,
  IconShieldCheck,
  IconPackage,
  IconClock,

} from '@tabler/icons-react';
import supabase from '../api/supabase';
import type { Material } from '../types';

/* ─── Category colors ────────────────────────────────────────── */
const CATEGORY_COLORS: Record<string, string> = {
  'Flooring': '#2dd4a8',
  'Walls': '#5e6ad2',
  'Doors': '#f97316',
  'Windows': '#38bdf8',
  'Furniture': '#a78bfa',
  'Ceiling': '#fb923c',
  'Plumbing': '#22d3ee',
  'Electrical': '#fbbf24',
  'Paint': '#e879f9',
  'Hardware': '#94a3b8',
};

const getCategoryColor = (cat: string) =>
  CATEGORY_COLORS[cat] || '#5c5e68';

/* ─── Format currency ────────────────────────────────────────── */
const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value);

/* ════════════════════════════════════════════════════════════════ */
/*  MATERIAL DETAIL MODAL                                         */
/* ════════════════════════════════════════════════════════════════ */
function MaterialDetailModal({
  material,
  opened,
  onClose,
}: {
  material: Material | null;
  opened: boolean;
  onClose: () => void;
}) {
  if (!material) return null;
  const catColor = getCategoryColor(material.category);

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={
        <Group gap="sm">
          <Box
            style={{
              width: 36,
              height: 36,
              borderRadius: '10px',
              background: `${catColor}15`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <IconPackage size={18} style={{ color: catColor }} />
          </Box>
          <div>
            <Text fw={600} size="sm">{material.name}</Text>
            <Text size="xs" c="dimmed">{material.brand}</Text>
          </div>
        </Group>
      }
      size="md"
      centered
    >
      <Stack gap="md">
        <Group gap="xs">
          <Badge color={catColor === '#5c5e68' ? 'gray' : 'accent'} variant="light">
            {material.category}
          </Badge>
          <Badge color="green" variant="light">
            {formatCurrency(material.rate)}/{material.unit}
          </Badge>
        </Group>

        <Divider />

        <Grid>
          <Grid.Col span={6}>
            <Text size="xs" c="dimmed">Brand</Text>
            <Text size="sm" fw={500}>{material.brand}</Text>
          </Grid.Col>
          <Grid.Col span={6}>
            <Text size="xs" c="dimmed">SKU</Text>
            <Text size="sm" fw={500} ff="monospace">{material.sku}</Text>
          </Grid.Col>
          <Grid.Col span={6}>
            <Text size="xs" c="dimmed">Unit</Text>
            <Text size="sm" fw={500}>{material.unit}</Text>
          </Grid.Col>
          <Grid.Col span={6}>
            <Text size="xs" c="dimmed">Lead Time</Text>
            <Text size="sm" fw={500}>{material.lead_time_days} days</Text>
          </Grid.Col>
        </Grid>

        {material.warranty && (
          <Group gap="xs">
            <IconShieldCheck size={14} style={{ color: 'var(--ace-success)' }} />
            <Text size="sm">Warranty: {material.warranty}</Text>
          </Group>
        )}
      </Stack>
    </Modal>
  );
}

/* ════════════════════════════════════════════════════════════════ */
/*  MAIN COMPONENT                                                */
/* ════════════════════════════════════════════════════════════════ */

export default function Materials() {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [detailMaterial, setDetailMaterial] = useState<Material | null>(null);
  const [detailOpened, setDetailOpened] = useState(false);

  /* ── Fetch materials from Supabase ───────────────────────── */
  const loadMaterials = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data, error } = await supabase
        .from('materials')
        .select('*')
        .order('name');

      if (error) throw error;
      setMaterials((data as Material[]) || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load materials';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMaterials();
  }, [loadMaterials]);

  /* ── Categories ───────────────────────────────────────────── */
  const categories = useMemo(() => {
    const cats = new Set(materials.map((m) => m.category).filter(Boolean));
    return Array.from(cats).sort();
  }, [materials]);

  /* ── Filtered materials ───────────────────────────────────── */
  const filteredMaterials = useMemo(() => {
    return materials.filter((m) => {
      const matchesSearch =
        m.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.brand.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.sku.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = !selectedCategory || m.category === selectedCategory;
      return matchesSearch && matchesCategory;
    });
  }, [materials, searchQuery, selectedCategory]);

  /* ── Handlers ─────────────────────────────────────────────── */
  const handleViewDetail = (material: Material) => {
    setDetailMaterial(material);
    setDetailOpened(true);
  };

  return (
    <Box p="lg" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* ══════ HEADER ══════ */}
      <Group justify="space-between" mb="lg" wrap="wrap" gap="sm" className="ace-animate-in">
        <div>
          <Group gap="xs" mb={4}>
            <Badge size="sm" variant="light" color="orange" leftSection={<IconBuildingStore size={12} />}>
              Module
            </Badge>
          </Group>
          <Title order={2} fw={700} style={{ letterSpacing: '-0.02em' }}>
            <span className="ace-gradient-text">Materials</span>
          </Title>
          <Text size="sm" c="dimmed" mt={2}>
            Browse and manage material catalogs and pricing
          </Text>
        </div>
        <Group gap="sm">
          <Tooltip label="Refresh">
            <ActionIcon variant="subtle" size="lg" onClick={loadMaterials} loading={loading}>
              <IconRefresh size={18} />
            </ActionIcon>
          </Tooltip>
        </Group>
      </Group>

      {/* ══════ SEARCH + FILTERS ══════ */}
      <Group gap="md" mb="lg" className="ace-animate-in" style={{ animationDelay: '100ms' }}>
        <TextInput
          placeholder="Search materials..."
          leftSection={<IconSearch size={16} />}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.currentTarget.value)}
          style={{ flex: 1, maxWidth: 400 }}
          variant="filled"
          size="sm"
        />
        <Group gap="xs">
          <Button
            size="xs"
            variant={selectedCategory === null ? 'filled' : 'subtle'}
            onClick={() => setSelectedCategory(null)}
          >
            All ({materials.length})
          </Button>
          {categories.map((cat) => (
            <Button
              key={cat}
              size="xs"
              variant={selectedCategory === cat ? 'filled' : 'subtle'}
              color={selectedCategory === cat ? 'accent' : 'gray'}
              onClick={() => setSelectedCategory(selectedCategory === cat ? null : cat)}
            >
              {cat}
            </Button>
          ))}
        </Group>
      </Group>

      {/* ══════ CONTENT ══════ */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        {loading ? (
          <Paper p="xl" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Stack align="center" gap="md">
              <Loader size="lg" color="accent" />
              <Text size="sm" c="dimmed">Loading materials catalog...</Text>
            </Stack>
          </Paper>
        ) : error ? (
          <Paper p="xl" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Stack align="center" gap="sm">
              <IconAlertCircle size={32} style={{ color: 'var(--ace-danger)' }} />
              <Text size="sm" style={{ color: 'var(--ace-danger)' }}>{error}</Text>
              <Button variant="subtle" size="xs" onClick={loadMaterials}>Retry</Button>
            </Stack>
          </Paper>
        ) : filteredMaterials.length === 0 ? (
          <Paper p="xl" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Stack align="center" gap="xs">
              <IconBuildingStore size={40} style={{ opacity: 0.1 }} />
              <Text size="sm" c="dimmed">No materials found</Text>
              <Text size="xs" c="dimmed">Try adjusting your search or filters</Text>
            </Stack>
          </Paper>
        ) : (
          <Grid gutter="md">
            {filteredMaterials.map((material, idx) => {
              const catColor = getCategoryColor(material.category);
              return (
                <Grid.Col key={material.id} span={{ base: 12, sm: 6, lg: 4, xl: 3 }}>
                  <Card
                    p="md"
                    className="ace-animate-in ace-card"
                    style={{ animationDelay: `${idx * 40}ms`, cursor: 'pointer' }}
                    onClick={() => handleViewDetail(material)}
                  >
                    <Stack gap="sm">
                      {/* Header */}
                      <Group justify="space-between" wrap="nowrap">
                        <Group gap="sm" wrap="nowrap">
                          <Box
                            style={{
                              width: 40,
                              height: 40,
                              borderRadius: '10px',
                              background: `${catColor}12`,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              flexShrink: 0,
                            }}
                          >
                            <IconPackage size={18} style={{ color: catColor }} />
                          </Box>
                          <div style={{ minWidth: 0 }}>
                            <Text size="sm" fw={600} lineClamp={1}>
                              {material.name}
                            </Text>
                            <Text size="xs" c="dimmed" lineClamp={1}>
                              {material.brand}
                            </Text>
                          </div>
                        </Group>
                      </Group>

                      {/* Category + SKU */}
                      <Group gap="xs">
                        <Badge size="xs" color={catColor === '#5c5e68' ? 'gray' : 'accent'} variant="light">
                          {material.category}
                        </Badge>
                        <Badge size="xs" variant="outline" color="gray" ff="monospace">
                          {material.sku}
                        </Badge>
                      </Group>

                      {/* Price */}
                      <Group justify="space-between" align="center">
                        <Text fw={700} size="lg" style={{ color: 'var(--ace-success)' }}>
                          {formatCurrency(material.rate)}
                        </Text>
                        <Text size="xs" c="dimmed">per {material.unit}</Text>
                      </Group>

                      {/* Details */}
                      <Group gap="md">
                        {material.lead_time_days > 0 && (
                          <Group gap={4}>
                            <IconClock size={12} style={{ color: 'var(--ace-text-tertiary)' }} />
                            <Text size="xs" c="dimmed">{material.lead_time_days}d lead</Text>
                          </Group>
                        )}
                        {material.warranty && (
                          <Group gap={4}>
                            <IconShieldCheck size={12} style={{ color: 'var(--ace-text-tertiary)' }} />
                            <Text size="xs" c="dimmed">{material.warranty}</Text>
                          </Group>
                        )}
                      </Group>
                    </Stack>
                  </Card>
                </Grid.Col>
              );
            })}
          </Grid>
        )}
      </div>

      {/* ══════ DETAIL MODAL ══════ */}
      <MaterialDetailModal
        material={detailMaterial}
        opened={detailOpened}
        onClose={() => setDetailOpened(false)}
      />
    </Box>
  );
}
