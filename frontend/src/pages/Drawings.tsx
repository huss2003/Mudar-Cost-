import { useEffect, useState, useCallback } from 'react';
import {
  Title,
  Text,
  Badge,
  Container,
  Grid,
  Card,
  Group,
  Stack,
  Loader,
  Alert,
  Button,
  ScrollArea,
  Tooltip,
  ActionIcon,
} from '@mantine/core';
import {
  IconComponents,
  IconAlertCircle,
  IconRefresh,
  IconRotate,
  IconFileUnknown,
} from '@tabler/icons-react';
import { fetchDrawings, fetchDrawingObjects } from '../api/drawings';
import type { Drawing, DetectedObject } from '../types';
import DrawingViewer2D from '../components/DrawingViewer2D';
import MaterialSelectorPanel from '../components/MaterialSelectorPanel';

export default function Drawings() {
  /* ── Drawings list ──────────────────────────────────────── */
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [drawingsLoading, setDrawingsLoading] = useState(true);
  const [drawingsError, setDrawingsError] = useState<string | null>(null);

  /* ── Selected drawing ───────────────────────────────────── */
  const [selectedDrawingId, setSelectedDrawingId] = useState<number | null>(
    null,
  );

  /* ── Objects for the selected drawing ────────────────────── */
  const [objects, setObjects] = useState<DetectedObject[]>([]);
  const [objectsLoading, setObjectsLoading] = useState(false);
  const [objectsError, setObjectsError] = useState<string | null>(null);

  /* ── Selected object (in viewer) ─────────────────────────── */
  const [selectedObject, setSelectedObject] = useState<DetectedObject | null>(
    null,
  );

  /* ── Fetch drawings ───────────────────────────────────────── */
  const loadDrawings = useCallback(async () => {
    setDrawingsLoading(true);
    setDrawingsError(null);
    try {
      const data = await fetchDrawings();
      setDrawings(data);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Failed to load drawings';
      setDrawingsError(msg);
    } finally {
      setDrawingsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDrawings();
  }, [loadDrawings]);

  /* ── Fetch objects for selected drawing ──────────────────── */
  const loadObjects = useCallback(async (drawingId: number) => {
    setObjectsLoading(true);
    setObjectsError(null);
    setSelectedObject(null);
    try {
      const data = await fetchDrawingObjects(drawingId);
      setObjects(data);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Failed to load drawing objects';
      setObjectsError(msg);
      setObjects([]);
    } finally {
      setObjectsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedDrawingId != null) {
      loadObjects(selectedDrawingId);
    } else {
      setObjects([]);
      setSelectedObject(null);
    }
  }, [selectedDrawingId, loadObjects]);

  /* ── Handlers ──────────────────────────────────────────────── */
  const handleDrawingClick = (drawingId: number) => {
    setSelectedDrawingId(drawingId);
  };

  const handleObjectSelect = (obj: DetectedObject) => {
    setSelectedObject(obj);
  };

  const handleCloseMaterialPanel = () => {
    setSelectedObject(null);
  };

  const handleMaterialSelected = (_materialId: number) => {
    // Could show a notification here
  };

  /* ── Derive the active boq_item_id ──────────────────────────── */
  const selectedBoqItemId = selectedObject?.boq_item_id ?? null;

  /* ── Render ─────────────────────────────────────────────────── */
  return (
    <Container size="xl" py="md" style={{ height: 'calc(100vh - 76px)' }}>
      <Stack style={{ height: '100%' }} gap="sm">
        {/* ── Header ─────────────────────────────────────────── */}
        <Group justify="space-between">
          <Group>
            <Badge size="lg" color="blue" mb={0}>
              Module
            </Badge>
            <Title order={3}>Drawings</Title>
          </Group>
          <Group>
            <Button
              variant="subtle"
              size="compact-sm"
              leftSection={<IconRefresh size={14} />}
              onClick={loadDrawings}
            >
              Refresh
            </Button>
          </Group>
        </Group>

        {/* ── Main content ─────────────────────────────────────── */}
        <div style={{ flex: 1, minHeight: 0 }}>
          <Grid style={{ height: '100%' }} gutter="sm">
            {/* ── Drawing list (left)
                 span=3 when material panel visible, span=2 otherwise ── */}
            <Grid.Col
              span={{ base: 12, md: selectedObject && selectedBoqItemId ? 3 : 2 }}
              style={{ height: '100%' }}
            >
              <Card
                p="sm"
                withBorder
                style={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <Group justify="space-between" mb="xs">
                  <Text size="sm" fw={600}>
                    Drawings
                  </Text>
                  {drawings.length > 0 && (
                    <Badge size="sm" variant="light" color="gray">
                      {drawings.length}
                    </Badge>
                  )}
                </Group>

                <ScrollArea style={{ flex: 1 }} offsetScrollbars>
                  {drawingsLoading && (
                    <Group justify="center" py="xl">
                      <Loader size="sm" />
                    </Group>
                  )}

                  {drawingsError && (
                    <Alert
                      icon={<IconAlertCircle size={16} />}
                      color="red"
                      p="xs"
                      title="Error"
                    >
                      <Text size="xs">{drawingsError}</Text>
                    </Alert>
                  )}

                  {!drawingsLoading && !drawingsError && drawings.length === 0 && (
                    <Stack align="center" py="xl" gap="xs">
                      <IconFileUnknown size={32} opacity={0.3} />
                      <Text size="sm" c="dimmed">
                        No drawings found
                      </Text>
                      <Text size="xs" c="dimmed" ta="center">
                        Upload CAD drawings to get started.
                      </Text>
                    </Stack>
                  )}

                  {!drawingsLoading &&
                    !drawingsError &&
                    drawings.map((d) => {
                      const isActive = d.id === selectedDrawingId;
                      return (
                        <Card
                          key={d.id}
                          p="xs"
                          withBorder={isActive}
                          mb={4}
                          style={{
                            cursor: 'pointer',
                            borderColor: isActive
                              ? 'var(--mantine-color-blue-6)'
                              : undefined,
                            background: isActive
                              ? 'var(--mantine-color-dark-5)'
                              : undefined,
                            transition: 'border-color 0.15s, background 0.15s',
                          }}
                          onClick={() => handleDrawingClick(d.id)}
                        >
                          <Group gap="xs" wrap="nowrap">
                            <IconComponents
                              size={16}
                              opacity={0.6}
                              style={{ flexShrink: 0 }}
                            />
                            <div style={{ minWidth: 0 }}>
                              <Text size="sm" fw={500} lineClamp={1}>
                                {d.name}
                              </Text>
                              <Group gap={4}>
                                <Badge
                                  size="xs"
                                  variant="outline"
                                  color={
                                    d.status === 'processed'
                                      ? 'green'
                                      : d.status === 'processing'
                                        ? 'yellow'
                                        : 'gray'
                                  }
                                >
                                  {d.status}
                                </Badge>
                                <Text size="xs" c="dimmed">
                                  {d.width_mm} × {d.height_mm} mm
                                </Text>
                              </Group>
                            </div>
                          </Group>
                        </Card>
                      );
                    })}
                </ScrollArea>
              </Card>
            </Grid.Col>

            {/* ── Viewer (center) ─────────────────────────────── */}
            <Grid.Col
              span={{
                base: 12,
                md:
                  selectedObject && selectedBoqItemId
                    ? 6
                    : selectedObject
                      ? 7
                      : 10,
              }}
              style={{ height: '100%' }}
            >
              {selectedDrawingId == null ? (
                <Card
                  p="xl"
                  withBorder
                  style={{
                    height: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Stack align="center" gap="xs">
                    <IconComponents size={48} opacity={0.2} />
                    <Text size="lg" fw={500} c="dimmed">
                      Select a drawing
                    </Text>
                    <Text size="sm" c="dimmed" ta="center">
                      Choose a drawing from the list to view its detected
                      objects.
                    </Text>
                  </Stack>
                </Card>
              ) : objectsLoading ? (
                <Card
                  p="xl"
                  withBorder
                  style={{
                    height: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Group>
                    <Loader size="sm" />
                    <Text size="sm" c="dimmed">
                      Loading objects...
                    </Text>
                  </Group>
                </Card>
              ) : objectsError ? (
                <Card
                  p="xl"
                  withBorder
                  style={{
                    height: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Stack align="center" gap="xs">
                    <IconAlertCircle size={32} color="red" />
                    <Text size="sm" c="red">
                      {objectsError}
                    </Text>
                    <Tooltip label="Retry">
                      <ActionIcon
                        variant="subtle"
                        onClick={() =>
                          selectedDrawingId && loadObjects(selectedDrawingId)
                        }
                      >
                        <IconRotate size={16} />
                      </ActionIcon>
                    </Tooltip>
                  </Stack>
                </Card>
              ) : (
                <div style={{ height: '100%' }}>
                  <DrawingViewer2D
                    drawingId={selectedDrawingId}
                    objects={objects}
                    onObjectSelect={handleObjectSelect}
                    selectedObjectId={selectedObject?.id ?? null}
                  />
                </div>
              )}
            </Grid.Col>

            {/* ── Material selector (right) ────────────────────── */}
            {selectedObject && selectedBoqItemId != null && (
              <Grid.Col
                span={{ base: 12, md: 3 }}
                style={{ height: '100%' }}
              >
                <div style={{ height: '100%' }}>
                  <MaterialSelectorPanel
                    object={selectedObject}
                    boqItemId={selectedBoqItemId}
                    onClose={handleCloseMaterialPanel}
                    onMaterialSelected={handleMaterialSelected}
                  />
                </div>
              </Grid.Col>
            )}
          </Grid>
        </div>
      </Stack>
    </Container>
  );
}
