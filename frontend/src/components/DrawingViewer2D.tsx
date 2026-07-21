import {
  useRef,
  useState,
  useCallback,
  useEffect,
  useMemo,
  type MouseEvent,
  type WheelEvent,
} from 'react';
import {
  Box,
  Group,
  Stack,
  Switch,
  ActionIcon,
  Tooltip,
  Paper,
  Text,
  Badge,
} from '@mantine/core';
import {
  IconZoomIn,
  IconZoomOut,
  IconMaximize,
  IconLayersIntersect,
} from '@tabler/icons-react';
import type { DrawingViewer2DProps, DetectedObject } from '../types';

/* ------------------------------------------------------------------ */
/*  Layer colours & human labels                                       */
/* ------------------------------------------------------------------ */
const LAYER_STYLES: Record<
  string,
  { fill: string; stroke: string; label: string }
> = {
  'A-WALL': { fill: '#555555', stroke: '#444444', label: 'Walls' },
  'A-PART': { fill: '#228be6', stroke: '#1c7ed6', label: 'Partitions' },
  'A-DOOR': { fill: '#e03131', stroke: '#c92a2a', label: 'Doors' },
  'A-WINDOW': { fill: '#15aabf', stroke: '#1098ad', label: 'Windows' },
  'A-FURN': { fill: '#f76707', stroke: '#e8590c', label: 'Furniture' },
  'A-TEXT': { fill: '#000000', stroke: '#000000', label: 'Text' },
};

const DEFAULT_LAYER = { fill: '#888888', stroke: '#666666', label: 'Other' };

function getLayerStyle(layer: string) {
  return LAYER_STYLES[layer] || DEFAULT_LAYER;
}

/* ------------------------------------------------------------------ */
/*  SVG rendering helpers                                              */
/* ------------------------------------------------------------------ */

function renderObject(
  obj: DetectedObject,
  scale: number,
  isSelected: boolean,
  isHovered: boolean,
) {
  const style = getLayerStyle(obj.layer);
  const x = obj.x * scale;
  const y = obj.y * scale;
  const w = Math.max(obj.width * scale, 2);
  const h = Math.max(obj.height * scale, 2);
  const strokeWidth = isSelected ? 3 : isHovered ? 2.5 : 1.5;
  const opacity = isSelected ? 1 : isHovered ? 0.9 : 0.75;
  const selectStyle = isSelected ? { filter: 'url(#glow)' } : {};
  const key = `obj-${obj.id}`;

  const baseProps = {
    key,
    'data-object-id': obj.id,
    style: { cursor: 'pointer', ...selectStyle } as React.CSSProperties,
    opacity,
  };

  const title = (
    <title>
      {obj.object_type}
      {obj.label ? ` — ${obj.label}` : ''}
      {'  '}
      {Math.round(obj.width)} × {Math.round(obj.height)} mm
      {obj.layer ? `  [${obj.layer}]` : ''}
    </title>
  );

  switch (obj.object_type) {
    /* ── Walls ─────────────────────────────────────────────── */
    case 'wall':
    case 'wall_1':
    case 'wall_2':
      return (
        <rect
          {...baseProps}
          x={x}
          y={y}
          width={w}
          height={h}
          fill={style.fill}
          fillOpacity={0.25}
          stroke={style.stroke}
          strokeWidth={strokeWidth}
          rx={1}
        >
          {title}
        </rect>
      );

    /* ── Partitions ────────────────────────────────────────── */
    case 'partition':
    case 'wall_partition':
      return (
        <rect
          {...baseProps}
          x={x}
          y={y}
          width={w}
          height={h}
          fill={style.fill}
          fillOpacity={0.15}
          stroke={style.stroke}
          strokeWidth={strokeWidth}
          strokeDasharray="8,4"
          rx={1}
        >
          {title}
        </rect>
      );

    /* ── Doors ─────────────────────────────────────────────── */
    case 'door':
    case 'door_swing': {
      // Door swing arc: hinge at (x, y+h), swing to (x+w, y+h)
      const hingeX = x;
      const hingeY = y + h;
      const swingR = Math.max(w, h);
      return (
        <g {...baseProps}>
          <line
            x1={hingeX}
            y1={hingeY}
            x2={x + w}
            y2={y + h}
            stroke={style.stroke}
            strokeWidth={strokeWidth + 1}
          />
          <path
            d={`M ${hingeX} ${hingeY} A ${swingR} ${swingR} 0 0 1 ${x + w} ${y}`}
            fill="none"
            stroke={style.stroke}
            strokeWidth={strokeWidth}
            strokeDasharray="4,2"
          />
          {title}
        </g>
      );
    }

    /* ── Windows ───────────────────────────────────────────── */
    case 'window':
    case 'window_opening':
      return (
        <g {...baseProps}>
          <rect
            x={x}
            y={y}
            width={w}
            height={h}
            fill="none"
            stroke={style.stroke}
            strokeWidth={strokeWidth}
          />
          <line
            x1={x}
            y1={y}
            x2={x + w}
            y2={y + h}
            stroke={style.stroke}
            strokeWidth={0.8}
          />
          <line
            x1={x + w}
            y1={y}
            x2={x}
            y2={y + h}
            stroke={style.stroke}
            strokeWidth={0.8}
          />
          {title}
        </g>
      );

    /* ── Furniture / Equipment ─────────────────────────────── */
    case 'furniture':
    case 'equipment':
    case 'fixture':
      return (
        <g {...baseProps}>
          <rect
            x={x}
            y={y}
            width={w}
            height={h}
            fill={style.fill}
            fillOpacity={0.3}
            stroke={style.stroke}
            strokeWidth={strokeWidth}
            rx={2}
          />
          {obj.label && (
            <text
              x={x + w / 2}
              y={y + h / 2}
              textAnchor="middle"
              dominantBaseline="central"
              fill={style.stroke}
              fontSize={Math.max(8, Math.min(14, w * 0.15))}
              pointerEvents="none"
              style={{ userSelect: 'none' }}
            >
              {obj.label}
            </text>
          )}
          {title}
        </g>
      );

    /* ── Room labels / text ────────────────────────────────── */
    case 'text':
    case 'room_label':
    case 'label':
      return (
        <text
          key={key}
          x={x}
          y={y}
          fill={style.stroke}
          fontSize={Math.max(8, Math.min(16, w * 0.12))}
          fontWeight={obj.object_type === 'room_label' ? 600 : 400}
          style={{ cursor: 'pointer' } as React.CSSProperties}
          data-object-id={obj.id}
        >
          {obj.label || `[${obj.object_type}]`}
          <title>
            {obj.object_type}
            {obj.label ? ` — ${obj.label}` : ''}
          </title>
        </text>
      );

    /* ── Electrical / symbols ──────────────────────────────── */
    case 'electrical':
    case 'symbol':
    case 'point':
      return (
        <circle
          {...baseProps}
          cx={x + w / 2}
          cy={y + h / 2}
          r={Math.max(w, h) / 2}
          fill={style.fill}
          fillOpacity={0.6}
          stroke={style.stroke}
          strokeWidth={strokeWidth}
        >
          {title}
        </circle>
      );

    /* ── Fallback ──────────────────────────────────────────── */
    default:
      return (
        <rect
          {...baseProps}
          x={x}
          y={y}
          width={w}
          height={h}
          fill={style.fill}
          fillOpacity={0.15}
          stroke={style.stroke}
          strokeWidth={strokeWidth}
          strokeDasharray="4,2"
          rx={1}
        >
          {title}
        </rect>
      );
  }
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function DrawingViewer2D({
  drawingId,
  objects,
  onObjectSelect,
  selectedObjectId,
  width: propWidth,
  height: propHeight,
}: DrawingViewer2DProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  /* dimensions */
  const [dimensions, setDimensions] = useState({ w: 800, h: 600 });

  /* pan / zoom */
  const [transform, setTransform] = useState({ x: 0, y: 0, scale: 1 });
  const isPanning = useRef(false);
  const panStart = useRef({ x: 0, y: 0 });
  const transformAtPanStart = useRef({ x: 0, y: 0, scale: 1 });
  const [hoveredId, setHoveredId] = useState<number | null>(null);

  /* layer visibility */
  const uniqueLayers = useMemo(() => {
    const set = new Set<string>();
    objects.forEach((o) => set.add(o.layer));
    return Array.from(set).sort();
  }, [objects]);

  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(
    () => new Set(uniqueLayers),
  );

  // sync visible layers when objects change
  useEffect(() => {
    setVisibleLayers((prev) => {
      const next = new Set(prev);
      uniqueLayers.forEach((l) => next.add(l));
      return next;
    });
  }, [uniqueLayers]);

  const visibleObjects = useMemo(
    () => objects.filter((o) => visibleLayers.has(o.layer)),
    [objects, visibleLayers],
  );

  /* resize observer */
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { inlineSize, blockSize } = entry.contentBoxSize[0];
        setDimensions({ w: inlineSize, h: blockSize });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  /* auto-fit to content */
  const fitToView = useCallback(() => {
    if (visibleObjects.length === 0 || dimensions.w === 0 || dimensions.h === 0)
      return;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    visibleObjects.forEach((o) => {
      const rx = o.x + (o.width || 1);
      const ry = o.y + (o.height || 1);
      if (o.x < minX) minX = o.x;
      if (o.y < minY) minY = o.y;
      if (rx > maxX) maxX = rx;
      if (ry > maxY) maxY = ry;
    });

    const bboxW = maxX - minX || 1000;
    const bboxH = maxY - minY || 1000;
    const padding = 60; // px

    const scaleX = (dimensions.w - padding * 2) / bboxW;
    const scaleY = (dimensions.h - padding * 2) / bboxH;
    const scale = Math.min(scaleX, scaleY);

    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    setTransform({
      x: dimensions.w / 2 - centerX * scale,
      y: dimensions.h / 2 - centerY * scale,
      scale: Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale)),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleObjects, dimensions]);

  // auto-fit on mount / when objects or dimensions change
  useEffect(() => {
    fitToView();
  }, [fitToView]);

  /* zoom controls */
  const zoomIn = () =>
    setTransform((t) => ({
      ...t,
      scale: Math.min(MAX_SCALE, t.scale * 1.3),
    }));
  const zoomOut = () =>
    setTransform((t) => ({
      ...t,
      scale: Math.max(MIN_SCALE, t.scale / 1.3),
    }));

  /* mouse pan */
  const handleMouseDown = useCallback((e: MouseEvent<SVGSVGElement>) => {
    // Don't start pan when clicking on an object
    if ((e.target as SVGElement).closest('[data-object-id]')) return;
    isPanning.current = true;
    panStart.current = { x: e.clientX, y: e.clientY };
    transformAtPanStart.current = { ...transform };
    // We read transform via ref below
  }, []);

  const handleMouseMove = useCallback(
    (e: MouseEvent<SVGSVGElement>) => {
      if (!isPanning.current) return;
      const dx = e.clientX - panStart.current.x;
      const dy = e.clientY - panStart.current.y;
      setTransform({
        x: transformAtPanStart.current.x + dx,
        y: transformAtPanStart.current.y + dy,
        scale: transformAtPanStart.current.scale,
      });
    },
    [],
  );

  const handleMouseUp = useCallback(() => {
    isPanning.current = false;
  }, []);

  /* wheel zoom */
  const handleWheel = useCallback(
    (e: WheelEvent<SVGSVGElement>) => {
      e.preventDefault();
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return;

      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const delta = -e.deltaY * 0.001;
      const newScale = Math.max(
        MIN_SCALE,
        Math.min(MAX_SCALE, transform.scale * (1 + delta)),
      );

      const ratio = newScale / transform.scale;
      setTransform({
        x: mouseX - ratio * (mouseX - transform.x),
        y: mouseY - ratio * (mouseY - transform.y),
        scale: newScale,
      });
    },
    [transform],
  );

  /* object click */
  const handleObjectClick = useCallback(
    (e: MouseEvent<SVGSVGElement>) => {
      const target = (e.target as SVGElement).closest('[data-object-id]');
      if (!target) return;
      const id = Number(target.getAttribute('data-object-id'));
      const obj = objects.find((o) => o.id === id);
      if (obj && onObjectSelect) onObjectSelect(obj);
    },
    [objects, onObjectSelect],
  );

  /* object hover */
  const handleObjectMouseOver = useCallback(
    (e: MouseEvent<SVGSVGElement>) => {
      const target = (e.target as SVGElement).closest('[data-object-id]');
      if (!target) return;
      setHoveredId(Number(target.getAttribute('data-object-id')));
    },
    [],
  );

  const handleObjectMouseOut = useCallback(() => {
    setHoveredId(null);
  }, []);

  /* toggle layer */
  const toggleLayer = (layer: string) => {
    setVisibleLayers((prev) => {
      const next = new Set(prev);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  };

  /* ── Render ──────────────────────────────────────────────── */
  const w = propWidth ?? dimensions.w;
  const h = propHeight ?? dimensions.h;

  return (
    <Box
      ref={containerRef}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        borderRadius: 'var(--mantine-radius-md)',
        background: '#1a1a1a',
        border: '1px solid var(--mantine-color-dark-4)',
      }}
      data-drawing-id={drawingId}
    >
      {/* ── Layer panel ─────────────────────────────────────── */}
      <Paper
        pos="absolute"
        top={8}
        left={8}
        p="xs"
        style={{ zIndex: 10, maxHeight: '90%', overflowY: 'auto' }}
        withBorder
      >
        <Group gap={4} mb={4}>
          <IconLayersIntersect size={14} />
          <Text size="xs" fw={600}>
            Layers
          </Text>
        </Group>
        <Stack gap={2}>
          {uniqueLayers.map((layer) => {
            const ls = getLayerStyle(layer);
            return (
              <Switch
                key={layer}
                size="xs"
                label={
                  <Group gap={4}>
                    <Badge
                      size="xs"
                      color={ls.stroke}
                      variant="filled"
                      style={{ backgroundColor: ls.stroke }}
                    />
                    <Text size="xs">{ls.label || layer}</Text>
                  </Group>
                }
                checked={visibleLayers.has(layer)}
                onChange={() => toggleLayer(layer)}
              />
            );
          })}
        </Stack>
      </Paper>

      {/* ── Zoom toolbar ────────────────────────────────────── */}
      <Paper
        pos="absolute"
        bottom={8}
        right={8}
        p={4}
        style={{ zIndex: 10 }}
        withBorder
      >
        <Stack gap={4}>
          <Tooltip label="Zoom in">
            <ActionIcon variant="subtle" size="sm" onClick={zoomIn}>
              <IconZoomIn size={16} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label="Zoom out">
            <ActionIcon variant="subtle" size="sm" onClick={zoomOut}>
              <IconZoomOut size={16} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label="Fit to view">
            <ActionIcon variant="subtle" size="sm" onClick={fitToView}>
              <IconMaximize size={16} />
            </ActionIcon>
          </Tooltip>
        </Stack>
      </Paper>

      {/* ── SVG ──────────────────────────────────────────────── */}
      <svg
        ref={svgRef}
        width={w}
        height={h}
        style={{
          cursor: isPanning.current ? 'grabbing' : 'grab',
          display: 'block',
        }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        onClick={handleObjectClick}
        onMouseOver={handleObjectMouseOver}
        onMouseOut={handleObjectMouseOut}
      >
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {visibleObjects.length === 0 ? (
          <text
            x={w / 2}
            y={h / 2}
            textAnchor="middle"
            dominantBaseline="central"
            fill="#666"
            fontSize={14}
          >
            {objects.length === 0
              ? 'No objects in this drawing'
              : 'All layers hidden'}
          </text>
        ) : (
          <g transform={`translate(${transform.x}, ${transform.y}) scale(${transform.scale})`}>
            {visibleObjects.map((obj) =>
              renderObject(
                obj,
                1, // scale is in the <g> transform
                obj.id === selectedObjectId,
                obj.id === hoveredId,
              ),
            )}
          </g>
        )}
      </svg>
    </Box>
  );
}

const MIN_SCALE = 0.05;
const MAX_SCALE = 50;
