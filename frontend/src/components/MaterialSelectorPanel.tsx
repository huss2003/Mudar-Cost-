import { useEffect, useState } from 'react';
import {
  Box,
  Card,
  Group,
  Stack,
  Text,
  Badge,
  Button,
  Loader,
  Title,
  ActionIcon,
  Divider,
  Tooltip,
} from '@mantine/core';
import {
  IconX,
  IconCheck,
  IconClock,
  IconShieldCheck,
  IconBuildingStore,
} from '@tabler/icons-react';
import { fetchMaterials, selectMaterial } from '../api/boq-items';
import type { Material, MaterialSelectorPanelProps } from '../types';

export default function MaterialSelectorPanel({
  object,
  boqItemId,
  onClose,
  onMaterialSelected,
}: MaterialSelectorPanelProps) {
  const [materials, setMaterials] = useState<Material[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectingId, setSelectingId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchMaterials(boqItemId)
      .then((data) => {
        if (!cancelled) setMaterials(data);
      })
      .catch((err) => {
        if (!cancelled)
          setError(
            err?.response?.data?.detail ||
              err?.message ||
              'Failed to load materials',
          );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [boqItemId]);

  const handleSelect = async (materialId: number) => {
    setSelectingId(materialId);
    try {
      await selectMaterial(boqItemId, materialId);
      onMaterialSelected(materialId);
    } catch {
      // Error is surfaced via caller if needed
    } finally {
      setSelectingId(null);
    }
  };

  /* ── Object detail header ────────────────────────────────── */
  return (
    <Box
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        borderLeft: '1px solid var(--mantine-color-dark-4)',
        background: 'var(--mantine-color-dark-7)',
      }}
    >
      {/* Header */}
      <Group justify="space-between" p="md" pb={0}>
        <Title order={5}>Material Selector</Title>
        <Tooltip label="Close panel">
          <ActionIcon variant="subtle" size="sm" onClick={onClose}>
            <IconX size={16} />
          </ActionIcon>
        </Tooltip>
      </Group>

      {/* Object info */}
      <Box p="md" pb={0}>
        <Card p="sm" withBorder>
          <Stack gap={4}>
            <Group gap={6}>
              <Badge size="sm" variant="light" color="blue">
                {object.object_type}
              </Badge>
              {object.layer && (
                <Badge size="sm" variant="outline" color="gray">
                  {object.layer}
                </Badge>
              )}
            </Group>
            {object.label && (
              <Text size="sm" fw={500}>
                {object.label}
              </Text>
            )}
            <Text size="xs" c="dimmed">
              {Math.round(object.width)} × {Math.round(object.height)} mm
              {object.properties?.material
                ? ` · ${object.properties.material}`
                : ''}
            </Text>
          </Stack>
        </Card>
      </Box>

      <Divider my="sm" />

      {/* Materials list */}
      <Box
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: 'var(--mantine-spacing-md)',
          paddingTop: 0,
        }}
      >
        {loading && (
          <Group justify="center" py="xl">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">
              Loading materials...
            </Text>
          </Group>
        )}

        {error && (
          <Text size="sm" c="red" ta="center" py="xl">
            {error}
          </Text>
        )}

        {!loading && !error && materials.length === 0 && (
          <Stack align="center" py="xl" gap="xs">
            <IconBuildingStore size={32} opacity={0.3} />
            <Text size="sm" c="dimmed" ta="center">
              No materials found
            </Text>
            <Text size="xs" c="dimmed" ta="center">
              No materials are currently catalogued for this item type.
            </Text>
          </Stack>
        )}

        {!loading &&
          !error &&
          materials.map((mat) => {
            const isSelected = selectingId === mat.id;
            return (
              <Card
                key={mat.id}
                p="sm"
                withBorder
                mb="sm"
                style={{ transition: 'border-color 0.15s' }}
              >
                <Stack gap={6}>
                  <Group justify="space-between" wrap="nowrap">
                    <Text size="sm" fw={600} lineClamp={1}>
                      {mat.name}
                    </Text>
                    <Badge
                      size="sm"
                      variant="light"
                      color={mat.rate > 0 ? 'green' : 'gray'}
                    >
                      ${mat.rate.toFixed(2)}/{mat.unit}
                    </Badge>
                  </Group>

                  <Group gap="xs" wrap="wrap">
                    <Badge
                      size="xs"
                      variant="outline"
                      color="gray"
                      leftSection={<IconBuildingStore size={10} />}
                    >
                      {mat.brand}
                    </Badge>
                    <Badge size="xs" variant="outline" color="gray">
                      SKU: {mat.sku}
                    </Badge>
                  </Group>

                  <Group gap="md">
                    {mat.lead_time_days > 0 && (
                      <Tooltip label="Lead time">
                        <Group gap={4}>
                          <IconClock size={12} opacity={0.5} />
                          <Text size="xs" c="dimmed">
                            {mat.lead_time_days} days
                          </Text>
                        </Group>
                      </Tooltip>
                    )}
                    {mat.warranty && (
                      <Tooltip label="Warranty">
                        <Group gap={4}>
                          <IconShieldCheck size={12} opacity={0.5} />
                          <Text size="xs" c="dimmed">
                            {mat.warranty}
                          </Text>
                        </Group>
                      </Tooltip>
                    )}
                  </Group>

                  <Button
                    size="xs"
                    variant="light"
                    color="blue"
                    fullWidth
                    leftSection={
                      isSelected ? (
                        <Loader size={12} />
                      ) : (
                        <IconCheck size={14} />
                      )
                    }
                    disabled={isSelected}
                    onClick={() => handleSelect(mat.id)}
                  >
                    {isSelected ? 'Selecting...' : 'Select Material'}
                  </Button>
                </Stack>
              </Card>
            );
          })}
      </Box>
    </Box>
  );
}
