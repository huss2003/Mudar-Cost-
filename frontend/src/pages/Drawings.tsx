import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Text,
  Badge,
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
  Title,
  Box,
  TextInput,
} from '@mantine/core';
import {
  IconComponents,
  IconAlertCircle,
  IconRefresh,
  IconRotate,
  IconUpload,
  IconSearch,
  IconFileCode,
  IconPhoto,
  IconLoader2,
  IconCheck,
  IconTrash,
} from '@tabler/icons-react';
import supabase from '../api/supabase';
import type { Drawing, DetectedObject } from '../types';
import DrawingViewer2D from '../components/DrawingViewer2D';
import MaterialSelectorPanel from '../components/MaterialSelectorPanel';

/* ─── Status helpers ──────────────────────────────────────────── */
const STATUS_CONFIG: Record<string, { color: string; label: string; icon: typeof IconCheck }> = {
  processed: { color: 'green', label: 'Complete', icon: IconCheck },
  processing: { color: 'yellow', label: 'Processing', icon: IconLoader2 },
  pending: { color: 'gray', label: 'Pending', icon: IconFileCode },
  uploaded: { color: 'blue', label: 'Uploaded', icon: IconUpload },
  error: { color: 'red', label: 'Error', icon: IconAlertCircle },
};

const formatDate = (dateStr: string): string => {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
};

export default function Drawings() {
  const fileInputRef = useRef<HTMLInputElement>(null);

  /* ── State ─────────────────────────────────────────────────── */
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [drawingsLoading, setDrawingsLoading] = useState(true);
  const [drawingsError, setDrawingsError] = useState<string | null>(null);
  const [selectedDrawingId, setSelectedDrawingId] = useState<number | null>(null);
  const [objects, setObjects] = useState<DetectedObject[]>([]);
  const [objectsLoading, setObjectsLoading] = useState(false);
  const [objectsError, setObjectsError] = useState<string | null>(null);
  const [selectedObject, setSelectedObject] = useState<DetectedObject | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<string>('');
  const [dragOver, setDragOver] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  /* ── Fetch drawings from Supabase ──────────────────────────── */
  const loadDrawings = useCallback(async () => {
    setDrawingsLoading(true);
    setDrawingsError(null);
    try {
      const { data, error } = await supabase
        .from('drawings')
        .select('*')
        .order('created_at', { ascending: false });

      if (error) throw error;
      setDrawings((data as Drawing[]) || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load drawings';
      setDrawingsError(msg);
    } finally {
      setDrawingsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDrawings();
  }, [loadDrawings]);

  /* ── Fetch detected objects ─────────────────────────────────── */
  const loadObjects = useCallback(async (drawingId: number) => {
    setObjectsLoading(true);
    setObjectsError(null);
    setSelectedObject(null);
    try {
      const { data, error } = await supabase
        .from('detected_objects')
        .select('*')
        .eq('drawing_id', drawingId);

      if (error) throw error;
      setObjects((data as DetectedObject[]) || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load objects';
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

  /* ── File upload ────────────────────────────────────────────── */
  const handleUpload = useCallback(async (file: File) => {
    setUploading(true);
    setUploadProgress('Uploading to storage...');

    try {
      const fileName = `${Date.now()}_${file.name.replace(/[^a-zA-Z0-9._-]/g, '_')}`;
      const filePath = `drawings/${fileName}`;

      // Upload to Supabase Storage
      const { error: storageError } = await supabase.storage
        .from('drawings')
        .upload(filePath, file, { contentType: file.type });

      if (storageError) {
        // If storage bucket doesn't exist, we still create the record
        console.warn('Storage upload failed, creating record without file:', storageError.message);
      }

      setUploadProgress('Creating drawing record...');

      // Get public URL or use the path
      let fileUrl = filePath;
      try {
        const { data: urlData } = supabase.storage.from('drawings').getPublicUrl(filePath);
        if (urlData?.publicUrl) fileUrl = urlData.publicUrl;
      } catch {
        // Use path as fallback
      }

      // Create drawing record in Supabase
      const { data: drawingData, error: insertError } = await supabase
        .from('drawings')
        .insert({
          name: file.name,
          file_path: fileUrl,
          file_size: file.size,
          width_mm: 0,
          height_mm: 0,
          status: 'uploaded',
        })
        .select()
        .single();

      if (insertError) throw insertError;

      setUploadProgress('Drawing uploaded successfully!');
      await loadDrawings();

      // Auto-select the newly uploaded drawing
      if (drawingData?.id) {
        setSelectedDrawingId(drawingData.id);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Upload failed';
      setDrawingsError(msg);
    } finally {
      setUploading(false);
      setUploadProgress('');
    }
  }, [loadDrawings]);

  /* ── Delete drawing ─────────────────────────────────────────── */
  const handleDelete = useCallback(async (drawingId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this drawing?')) return;

    try {
      const { error } = await supabase.from('drawings').delete().eq('id', drawingId);
      if (error) throw error;
      if (selectedDrawingId === drawingId) {
        setSelectedDrawingId(null);
        setObjects([]);
        setSelectedObject(null);
      }
      await loadDrawings();
    } catch (err: unknown) {
      console.error('Delete failed:', err);
    }
  }, [selectedDrawingId, loadDrawings]);

  /* ── Drag handlers ──────────────────────────────────────────── */
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleUpload(file);
  }, [handleUpload]);

  /* ── Filtered drawings ──────────────────────────────────────── */
  const filteredDrawings = drawings.filter((d) =>
    d.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const selectedBoqItemId = selectedObject?.boq_item_id ?? null;

  /* ── Render ─────────────────────────────────────────────────── */
  return (
    <Box p="lg" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".dwg,.dxf,.pdf,.png,.jpg,.jpeg,.svg"
        style={{ display: 'none' }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleUpload(file);
          e.target.value = '';
        }}
      />

      {/* ══════ HEADER ══════ */}
      <Group justify="space-between" mb="lg" wrap="wrap" gap="sm" className="ace-animate-in">
        <div>
          <Group gap="xs" mb={4}>
            <Badge
              size="sm"
              variant="light"
              color="blue"
              leftSection={<IconComponents size={12} />}
            >
              Module
            </Badge>
          </Group>
          <Title order={2} fw={700} style={{ letterSpacing: '-0.02em' }}>
            <span className="ace-gradient-text">Drawings</span>
          </Title>
          <Text size="sm" c="dimmed" mt={2}>
            Upload and analyze construction drawings
          </Text>
        </div>
        <Group gap="sm">
          <Tooltip label="Refresh drawings">
            <ActionIcon
              variant="subtle"
              size="lg"
              onClick={loadDrawings}
              loading={drawingsLoading}
            >
              <IconRefresh size={18} />
            </ActionIcon>
          </Tooltip>
          <Button
            leftSection={<IconUpload size={16} />}
            onClick={() => fileInputRef.current?.click()}
            loading={uploading}
            variant="gradient"
            gradient={{ from: 'accent', to: 'cyan', deg: 135 }}
          >
            Upload Drawing
          </Button>
        </Group>
      </Group>

      {/* ══════ MAIN CONTENT ══════ */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <Grid style={{ height: '100%' }} gutter="md">
          {/* ── Drawing list sidebar ───────────────────────── */}
          <Grid.Col
            span={{ base: 12, md: selectedObject && selectedBoqItemId ? 3 : 2 }}
            style={{ height: '100%' }}
          >
            <Card
              p="sm"
              style={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              {/* Search */}
              <TextInput
                placeholder="Search drawings..."
                size="xs"
                leftSection={<IconSearch size={14} />}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.currentTarget.value)}
                mb="sm"
                variant="filled"
              />

              <Group justify="space-between" mb="xs">
                <Text size="xs" fw={600} c="dimmed" tt="uppercase" style={{ letterSpacing: '0.06em' }}>
                  All Drawings
                </Text>
                {filteredDrawings.length > 0 && (
                  <Badge size="xs" variant="light" color="gray" circle>
                    {filteredDrawings.length}
                  </Badge>
                )}
              </Group>

              {/* Upload zone */}
              <Box
                className="ace-upload-zone"
                data-active={dragOver}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                style={{ padding: '16px 12px', marginBottom: 8 }}
              >
                <IconUpload
                  size={20}
                  style={{ color: dragOver ? 'var(--ace-accent)' : 'var(--ace-text-tertiary)', marginBottom: 4 }}
                />
                <Text size="xs" c="dimmed">
                  {dragOver ? 'Drop to upload' : 'Drag or click'}
                </Text>
              </Box>

              {uploading && (
                <Card p="xs" mb="sm" style={{ background: 'rgba(94,106,210,0.08)', borderColor: 'rgba(94,106,210,0.2)' }}>
                  <Group gap="xs">
                    <Loader size={12} color="accent" />
                    <Text size="xs" c="accent">{uploadProgress}</Text>
                  </Group>
                </Card>
              )}

              {/* Drawing list */}
              <ScrollArea style={{ flex: 1 }} offsetScrollbars>
                {drawingsLoading ? (
                  <Group justify="center" py="xl">
                    <Loader size="sm" />
                  </Group>
                ) : drawingsError ? (
                  <Alert icon={<IconAlertCircle size={16} />} color="red" p="xs" title="Error">
                    <Text size="xs">{drawingsError}</Text>
                  </Alert>
                ) : filteredDrawings.length === 0 ? (
                  <Stack align="center" py="xl" gap="xs">
                    <IconFileCode size={32} style={{ opacity: 0.15 }} />
                    <Text size="sm" c="dimmed" ta="center">
                      {searchQuery ? 'No matching drawings' : 'No drawings yet'}
                    </Text>
                    <Text size="xs" c="dimmed" ta="center">
                      {searchQuery ? 'Try a different search' : 'Upload your first drawing to get started'}
                    </Text>
                  </Stack>
                ) : (
                  filteredDrawings.map((d, idx) => {
                    const isActive = d.id === selectedDrawingId;
                    const statusCfg = STATUS_CONFIG[d.status] || STATUS_CONFIG.pending;
                    return (
                      <Card
                        key={d.id}
                        p="xs"
                        mb={4}
                        className="ace-animate-slide"
                        style={{
                          animationDelay: `${idx * 30}ms`,
                          cursor: 'pointer',
                          borderLeft: isActive ? `3px solid ${statusCfg.color === 'green' ? '#2dd4a8' : statusCfg.color === 'yellow' ? '#f5a623' : '#5e6ad2'}` : '3px solid transparent',
                          background: isActive ? 'rgba(94,106,210,0.06)' : undefined,
                          borderColor: isActive ? 'var(--ace-accent)' : undefined,
                        }}
                        onClick={() => setSelectedDrawingId(d.id)}
                      >
                        <Group gap="xs" wrap="nowrap">
                          <Box
                            style={{
                              width: 36,
                              height: 36,
                              borderRadius: '8px',
                              background: isActive
                                ? 'linear-gradient(135deg, rgba(94,106,210,0.2), rgba(167,139,250,0.1))'
                                : 'rgba(255,255,255,0.03)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              flexShrink: 0,
                            }}
                          >
                            <IconPhoto size={16} style={{ color: isActive ? '#5e6ad2' : '#5c5e68' }} />
                          </Box>
                          <div style={{ minWidth: 0, flex: 1 }}>
                            <Text size="xs" fw={600} lineClamp={1}>
                              {d.name}
                            </Text>
                            <Group gap={4} mt={2}>
                              <Badge
                                size="xs"
                                color={statusCfg.color}
                                variant="dot"
                                style={{ textTransform: 'none' }}
                              >
                                {statusCfg.label}
                              </Badge>
                              <Text size="xs" c="dimmed">
                                {formatDate(d.created_at)}
                              </Text>
                            </Group>
                          </div>
                          <Tooltip label="Delete">
                            <ActionIcon
                              size="xs"
                              variant="subtle"
                              color="red"
                              onClick={(e) => handleDelete(d.id, e)}
                              style={{ opacity: 0.5 }}
                              className="ace-btn"
                            >
                              <IconTrash size={12} />
                            </ActionIcon>
                          </Tooltip>
                        </Group>
                      </Card>
                    );
                  })
                )}
              </ScrollArea>
            </Card>
          </Grid.Col>

          {/* ── Viewer ────────────────────────────────────── */}
          <Grid.Col
            span={{
              base: 12,
              md: selectedObject && selectedBoqItemId ? 6 : selectedObject ? 7 : 10,
            }}
            style={{ height: '100%' }}
          >
            {selectedDrawingId == null ? (
              <Card
                p="xl"
                style={{
                  height: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Stack align="center" gap="md" className="ace-animate-in">
                  <Box
                    style={{
                      width: 80,
                      height: 80,
                      borderRadius: '20px',
                      background: 'linear-gradient(135deg, rgba(94,106,210,0.1), rgba(167,139,250,0.05))',
                      border: '1px dashed rgba(94,106,210,0.2)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <IconComponents size={32} style={{ color: 'rgba(94,106,210,0.3)' }} />
                  </Box>
                  <div style={{ textAlign: 'center' }}>
                    <Text size="lg" fw={600} c="dimmed">
                      Select a drawing
                    </Text>
                    <Text size="sm" c="dimmed" mt={4}>
                      Choose a drawing from the list or upload a new one
                    </Text>
                  </div>
                </Stack>
              </Card>
            ) : objectsLoading ? (
              <Card
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
                  <Text size="sm" c="dimmed">Analyzing drawing objects...</Text>
                </Stack>
              </Card>
            ) : objectsError ? (
              <Card
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
                  <Text size="sm" style={{ color: 'var(--ace-danger)' }}>
                    {objectsError}
                  </Text>
                  <Tooltip label="Retry">
                    <ActionIcon
                      variant="subtle"
                      onClick={() => selectedDrawingId && loadObjects(selectedDrawingId)}
                      className="ace-btn"
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
                  onObjectSelect={setSelectedObject}
                  selectedObjectId={selectedObject?.id ?? null}
                />
              </div>
            )}
          </Grid.Col>

          {/* ── Material selector panel ───────────────────── */}
          {selectedObject && selectedBoqItemId != null && (
            <Grid.Col span={{ base: 12, md: 3 }} style={{ height: '100%' }}>
              <div style={{ height: '100%' }}>
                <MaterialSelectorPanel
                  object={selectedObject}
                  boqItemId={selectedBoqItemId}
                  onClose={() => setSelectedObject(null)}
                  onMaterialSelected={() => {}}
                />
              </div>
            </Grid.Col>
          )}
        </Grid>
      </div>
    </Box>
  );
}
