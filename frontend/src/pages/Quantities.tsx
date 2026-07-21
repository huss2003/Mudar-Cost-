import { useState, useMemo } from 'react';
import {
  Title,
  Text,
  Badge,
  Container,
  Paper,
  Grid,
  Group,
  Stack,
  Table,
  SegmentedControl,
  Tooltip,
} from '@mantine/core';
import { IconBox, IconLayoutBoard, IconInfoCircle } from '@tabler/icons-react';
import ThreeViewer from '../components/ThreeViewer';
import FinishPresetSelector from '../components/FinishPresetSelector';
import type { DetectedObject, FinishPreset } from '../types';

// Demo objects to populate the 3D viewer
let _nextId = 100;
function nextId(): number {
  return _nextId++;
}

const DEMO_OBJECTS: DetectedObject[] = [
  // Outer walls — a rectangular room
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'exterior-wall',
    label: 'North Wall',
    x: 0, y: 1.5,
    width: 10, height: 3,
    layer: 'walls',
    type: 'wall',
    dimensions: { length: 10, height: 3, thickness: 0.25 },
  },
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'exterior-wall',
    label: 'South Wall',
    x: 0, y: 1.5,
    width: 10, height: 3,
    layer: 'walls',
    type: 'wall',
    position: { x: 0, y: 1.5, z: 5 },
    dimensions: { length: 10, height: 3, thickness: 0.25 },
  },
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'exterior-wall',
    label: 'East Wall',
    x: 5, y: 1.5,
    width: 10, height: 3,
    layer: 'walls',
    type: 'wall',
    position: { x: 5, y: 1.5, z: 0 },
    dimensions: { length: 10, height: 3, thickness: 0.25 },
    rotation3d: { x: 0, y: Math.PI / 2, z: 0 },
  },
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'exterior-wall',
    label: 'West Wall',
    x: -5, y: 1.5,
    width: 10, height: 3,
    layer: 'walls',
    type: 'wall',
    position: { x: -5, y: 1.5, z: 0 },
    dimensions: { length: 10, height: 3, thickness: 0.25 },
    rotation3d: { x: 0, y: Math.PI / 2, z: 0 },
  },
  // Interior partition
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'partition',
    label: 'Interior Wall',
    x: 0, y: 1.5,
    width: 6, height: 2.8,
    layer: 'partitions',
    type: 'partition',
    position: { x: 0, y: 1.5, z: 0 },
    dimensions: { length: 6, height: 2.8, thickness: 0.12 },
    rotation3d: { x: 0, y: Math.PI / 4, z: 0 },
  },
  // Door
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'door',
    label: 'Main Door',
    x: 0, y: 1.1,
    width: 0.9, height: 2.1,
    layer: 'doors',
    type: 'door',
    position: { x: 0, y: 1.1, z: 4.9 },
    dimensions: { length: 0.9, height: 2.1, thickness: 0.1 },
  },
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'door',
    label: 'Side Door',
    x: 4.9, y: 1.1,
    width: 0.8, height: 2.1,
    layer: 'doors',
    type: 'door',
    position: { x: 4.9, y: 1.1, z: -2 },
    dimensions: { length: 0.8, height: 2.1, thickness: 0.1 },
    rotation3d: { x: 0, y: Math.PI / 2, z: 0 },
  },
  // Windows
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'window',
    label: 'North Window',
    x: -2, y: 1.5,
    width: 1.5, height: 1.2,
    layer: 'windows',
    type: 'window',
    position: { x: -2, y: 1.5, z: -4.9 },
    dimensions: { length: 1.5, height: 1.2, thickness: 0.08 },
  },
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'window',
    label: 'South Window',
    x: 2, y: 1.5,
    width: 1.5, height: 1.2,
    layer: 'windows',
    type: 'window',
    position: { x: 2, y: 1.5, z: 4.9 },
    dimensions: { length: 1.5, height: 1.2, thickness: 0.08 },
  },
  // Furniture
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'furniture',
    label: 'Table',
    x: -2, y: 1.5,
    width: 1.8, height: 0.8,
    layer: 'furniture',
    type: 'furniture',
    position: { x: -2, y: 0.4, z: -1.5 },
    dimensions: { length: 1.8, height: 0.8, thickness: 1.2 },
  },
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'furniture',
    label: 'Desk',
    x: 2.5, y: 1.5,
    width: 1.2, height: 0.7,
    layer: 'furniture',
    type: 'furniture',
    position: { x: 2.5, y: 0.35, z: 1.5 },
    dimensions: { length: 1.2, height: 0.7, thickness: 0.6 },
  },
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'furniture',
    label: 'Cabinet',
    x: -3.5, y: 1.5,
    width: 0.8, height: 1.6,
    layer: 'furniture',
    type: 'furniture',
    position: { x: -3.5, y: 0.8, z: 3 },
    dimensions: { length: 0.8, height: 1.6, thickness: 0.5 },
  },
  // Room labels
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'room',
    label: 'Main Hall',
    x: 0, y: 0.1,
    width: 8, height: 10,
    layer: 'rooms',
    type: 'room',
    position: { x: 0, y: 0.1, z: -1.5 },
  },
  {
    id: nextId(),
    drawing_id: 1,
    object_type: 'room',
    label: 'Office',
    x: 2.5, y: 0.1,
    width: 3, height: 4,
    layer: 'rooms',
    type: 'room',
    position: { x: 2.5, y: 0.1, z: -3.5 },
  },
];

// Sample BOQ table data
interface BoqItem {
  category: string;
  description: string;
  quantity: number;
  unit: string;
  rate: number;
  total: number;
}

const SAMPLE_BOQ: BoqItem[] = [
  { category: 'Walls', description: 'Brick wall 9" thick', quantity: 86.5, unit: 'm²', rate: 850, total: 73525 },
  { category: 'Partitions', description: 'Gypboard partition 4"', quantity: 28.0, unit: 'm²', rate: 450, total: 12600 },
  { category: 'Doors', description: 'Flush door 0.9×2.1m', quantity: 2, unit: 'nos', rate: 8500, total: 17000 },
  { category: 'Windows', description: 'Aluminium sliding', quantity: 2, unit: 'nos', rate: 12500, total: 25000 },
  { category: 'Flooring', description: 'Vitrified tiles 600×600', quantity: 48.0, unit: 'm²', rate: 980, total: 47040 },
  { category: 'Furniture', description: 'Workstations (modular)', quantity: 3, unit: 'nos', rate: 22000, total: 66000 },
];

const BOQ_TOTAL = SAMPLE_BOQ.reduce((sum, item) => sum + item.total, 0);

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value);

function BoqTable() {
  const rows = SAMPLE_BOQ.map((item, idx) => (
    <Table.Tr key={idx}>
      <Table.Td>
        <Badge variant="light" size="sm">
          {item.category}
        </Badge>
      </Table.Td>
      <Table.Td>{item.description}</Table.Td>
      <Table.Td ta="right">{item.quantity}</Table.Td>
      <Table.Td>{item.unit}</Table.Td>
      <Table.Td ta="right">{formatCurrency(item.rate)}</Table.Td>
      <Table.Td ta="right">{formatCurrency(item.total)}</Table.Td>
    </Table.Tr>
  ));

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
      <Table.Tbody>{rows}</Table.Tbody>
      <Table.Tfoot>
        <Table.Tr>
          <Table.Th colSpan={5} ta="right">
            <Text fw={700}>Grand Total</Text>
          </Table.Th>
          <Table.Th ta="right">
            <Text fw={700}>{formatCurrency(BOQ_TOTAL)}</Text>
          </Table.Th>
        </Table.Tr>
      </Table.Tfoot>
    </Table>
  );
}

export default function Quantities() {
  const [viewMode, setViewMode] = useState<'3d' | '2d'>('3d');
  const [finishPreset, setFinishPreset] = useState<FinishPreset>('modern');

  const objects = useMemo(() => DEMO_OBJECTS, []);

  return (
    <Container size="xl" py="md">
      {/* Header */}
      <Group justify="space-between" mb="md">
        <div>
          <Badge size="lg" color="cyan" mb="xs">
            Module
          </Badge>
          <Title order={2}>Quantities</Title>
          <Text c="dimmed" size="sm">
            Review quantity takeoffs and visualize objects in 3D
          </Text>
        </div>
        <Group gap="sm">
          <Tooltip label="Switch between 2D table and 3D scene view">
            <SegmentedControl
              value={viewMode}
              onChange={(val) => setViewMode(val as '3d' | '2d')}
              data={[
                {
                  value: '3d',
                  label: (
                    <Group gap={4} wrap="nowrap">
                      <IconBox size={16} />
                      <Text size="sm">3D</Text>
                    </Group>
                  ),
                },
                {
                  value: '2d',
                  label: (
                    <Group gap={4} wrap="nowrap">
                      <IconLayoutBoard size={16} />
                      <Text size="sm">2D</Text>
                    </Group>
                  ),
                },
              ]}
              size="sm"
            />
          </Tooltip>
        </Group>
      </Group>

      {/* Finish Preset Selector */}
      <Paper p="sm" withBorder mb="md">
        <Group justify="space-between" align="center">
          <Group gap="xs">
            <IconInfoCircle size={16} color="gray" />
            <Text size="sm" c="dimmed">
              Finish Preset
            </Text>
          </Group>
          <div style={{ flex: 1, maxWidth: 500 }}>
            <FinishPresetSelector
              value={finishPreset}
              onChange={setFinishPreset}
            />
          </div>
        </Group>
      </Paper>

      {viewMode === '3d' ? (
        /* 3D View: 3D scene on left, BOQ on right */
        <Grid gutter="md">
          <Grid.Col span={{ base: 12, md: 7 }}>
            <Paper p={0} withBorder style={{ overflow: 'hidden' }}>
              <div style={{ height: '520px' }}>
                <ThreeViewer
                  objects={objects}
                  finishPreset={finishPreset}
                  onObjectClick={(obj) => {
                    console.log('Object clicked:', obj);
                  }}
                />
              </div>
            </Paper>
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 5 }}>
            <Paper p="md" withBorder>
              <Stack gap="sm">
                <Group justify="space-between">
                  <Text fw={600} size="sm">
                    Bill of Quantities
                  </Text>
                  <Badge size="sm" color="green">
                    {SAMPLE_BOQ.length} items
                  </Badge>
                </Group>
                <div style={{ maxHeight: 460, overflowY: 'auto' }}>
                  <BoqTable />
                </div>
              </Stack>
            </Paper>
          </Grid.Col>
        </Grid>
      ) : (
        /* 2D View: Full width BOQ table */
        <Paper p="md" withBorder>
          <Stack gap="sm">
            <Group justify="space-between">
              <Text fw={600} size="sm">
                Bill of Quantities
              </Text>
              <Badge size="sm" color="green">
                {SAMPLE_BOQ.length} items
              </Badge>
            </Group>
            <BoqTable />
          </Stack>
        </Paper>
      )}

      {/* Objects summary badge */}
      <Paper p="sm" withBorder mt="md">
        <Group gap="xs">
          <IconInfoCircle size={16} color="gray" />
          <Text size="xs" c="dimmed">
            {objects.length} detected objects · Click any object in the 3D
            scene to inspect it
          </Text>
        </Group>
      </Paper>
    </Container>
  );
}
