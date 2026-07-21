import { useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Text, useTexture } from '@react-three/drei';
import * as THREE from 'three';
import type { DetectedObject, FinishPreset } from '../types';
import { FINISH_PRESETS } from '../types';

interface ThreeViewerProps {
  objects: DetectedObject[];
  onObjectClick?: (obj: DetectedObject) => void;
  finishPreset?: FinishPreset;
  materialTextures?: Record<string, string>;
}

const FLOOR_SIZE = 50;

interface ParsedObjects {
  walls: DetectedObject[];
  partitions: DetectedObject[];
  doors: DetectedObject[];
  windows: DetectedObject[];
  furniture: DetectedObject[];
  rooms: DetectedObject[];
  others: DetectedObject[];
}

function resolveType(obj: DetectedObject): DetectedObject['type'] {
  if (obj.type) return obj.type;
  const ot = (obj.object_type || '').toLowerCase();
  if (ot.includes('wall') || ot.includes('exterior')) return 'wall';
  if (ot.includes('partition') || ot.includes('interior')) return 'partition';
  if (ot.includes('door')) return 'door';
  if (ot.includes('window')) return 'window';
  if (ot.includes('furniture') || ot.includes('table') || ot.includes('chair')) return 'furniture';
  if (ot.includes('room') || ot.includes('hall') || ot.includes('office')) return 'room';
  return 'other';
}

function resolvePosition(obj: DetectedObject): { x: number; y: number; z: number } {
  if (obj.position) return obj.position;
  return { x: obj.x || 0, y: 0, z: obj.y || 0 };
}

function resolveDimensions(obj: DetectedObject): { length: number; height: number; thickness: number } {
  if (obj.dimensions) return obj.dimensions;
  return { length: obj.width || 2, height: obj.height || 2, thickness: 0.2 };
}

function resolveRotation3d(obj: DetectedObject): { x: number; y: number; z: number } {
  if (obj.rotation3d) return obj.rotation3d;
  if (obj.rotation !== undefined) return { x: 0, y: obj.rotation, z: 0 };
  return { x: 0, y: 0, z: 0 };
}

function parseObjects(objects: DetectedObject[]): ParsedObjects {
  const parsed: ParsedObjects = {
    walls: [],
    partitions: [],
    doors: [],
    windows: [],
    furniture: [],
    rooms: [],
    others: [],
  };

  for (const obj of objects) {
    switch (resolveType(obj)) {
      case 'wall':
        parsed.walls.push(obj);
        break;
      case 'partition':
        parsed.partitions.push(obj);
        break;
      case 'door':
        parsed.doors.push(obj);
        break;
      case 'window':
        parsed.windows.push(obj);
        break;
      case 'furniture':
        parsed.furniture.push(obj);
        break;
      case 'room':
        parsed.rooms.push(obj);
        break;
      default:
        parsed.others.push(obj);
        break;
    }
  }

  return parsed;
}

function safeDim(dim: number | undefined | null, fallback: number): number {
  const val = dim ?? fallback;
  return val <= 0 ? fallback : val;
}

function WallMesh({
  obj,
  preset,
  textureUrl,
  onClick,
}: {
  obj: DetectedObject;
  preset: FinishPreset;
  textureUrl?: string;
  onClick?: (obj: DetectedObject) => void;
}) {
  const colors = FINISH_PRESETS[preset];
  const dim = resolveDimensions(obj);
  const length = safeDim(dim.length, 4);
  const height = safeDim(dim.height, 3);
  const thickness = safeDim(dim.thickness, 0.25);

  const pos = resolvePosition(obj);
  const rot = resolveRotation3d(obj);

  const texture = textureUrl ? useTexture(textureUrl) : null;

  return (
    <mesh
      position={[pos.x, pos.y, pos.z]}
      rotation={[rot.x, rot.y, rot.z]}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(obj);
      }}
    >
      <boxGeometry args={[length, height, thickness]} />
      {texture ? (
        <meshStandardMaterial
          map={texture}
          metalness={colors.metalness}
          roughness={colors.roughness}
        />
      ) : (
        <meshStandardMaterial
          color={colors.wallColor}
          metalness={colors.metalness}
          roughness={colors.roughness}
        />
      )}
    </mesh>
  );
}

function DoorMesh({
  obj,
  preset,
  onClick,
}: {
  obj: DetectedObject;
  preset: FinishPreset;
  onClick?: (obj: DetectedObject) => void;
}) {
  const colors = FINISH_PRESETS[preset];
  const dim = resolveDimensions(obj);
  const width = safeDim(dim.length, 1);
  const height = safeDim(dim.height, 2.1);
  const depth = safeDim(dim.thickness, 0.1);

  const pos = resolvePosition(obj);
  const rot = resolveRotation3d(obj);

  return (
    <mesh
      position={[pos.x, pos.y, pos.z]}
      rotation={[rot.x, rot.y, rot.z]}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(obj);
      }}
    >
      <boxGeometry args={[width, height, depth]} />
      <meshStandardMaterial
        color={colors.accentColor}
        metalness={0.4}
        roughness={0.3}
      />
    </mesh>
  );
}

function WindowMesh({
  obj,
  preset,
  onClick,
}: {
  obj: DetectedObject;
  preset: FinishPreset;
  onClick?: (obj: DetectedObject) => void;
}) {
  const colors = FINISH_PRESETS[preset];
  const dim = resolveDimensions(obj);
  const width = safeDim(dim.length, 1.5);
  const height = safeDim(dim.height, 1.2);
  const depth = safeDim(dim.thickness, 0.1);

  const pos = resolvePosition(obj);
  const rot = resolveRotation3d(obj);

  return (
    <mesh
      position={[pos.x, pos.y, pos.z]}
      rotation={[rot.x, rot.y, rot.z]}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(obj);
      }}
    >
      <boxGeometry args={[width, height, depth]} />
      <meshPhysicalMaterial
        color={colors.accentColor}
        transparent
        opacity={0.3}
        metalness={0.1}
        roughness={0.05}
        envMapIntensity={0.5}
      />
    </mesh>
  );
}

function FurnitureMesh({
  obj,
  preset,
  onClick,
}: {
  obj: DetectedObject;
  preset: FinishPreset;
  onClick?: (obj: DetectedObject) => void;
}) {
  const colors = FINISH_PRESETS[preset];
  const dim = resolveDimensions(obj);
  const length = safeDim(dim.length, 1);
  const height = safeDim(dim.height, 0.8);
  const width = safeDim(dim.thickness, 0.8);

  const pos = resolvePosition(obj);
  const rot = resolveRotation3d(obj);

  return (
    <mesh
      position={[pos.x, pos.y, pos.z]}
      rotation={[rot.x, rot.y, rot.z]}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(obj);
      }}
    >
      <boxGeometry args={[length, height, width]} />
      <meshStandardMaterial
        color={colors.accentColor}
        metalness={0.3}
        roughness={0.5}
      />
    </mesh>
  );
}

function FloorMesh({ preset }: { preset: FinishPreset }) {
  const colors = FINISH_PRESETS[preset];

  const gridHelper = useMemo(() => {
    const size = FLOOR_SIZE;
    const divisions = 20;
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 512;
    const ctx = canvas.getContext('2d');
    if (!ctx) return new THREE.CanvasTexture(canvas);

    ctx.fillStyle = colors.floorColor;
    ctx.fillRect(0, 0, 512, 512);

    ctx.strokeStyle = '#000000';
    ctx.globalAlpha = 0.08;
    ctx.lineWidth = 1;
    const step = 512 / divisions;
    for (let i = 0; i <= divisions; i++) {
      const x = i * step;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, 512);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, x);
      ctx.lineTo(512, x);
      ctx.stroke();
    }

    const tex = new THREE.CanvasTexture(canvas);
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(size / 2, size / 2);
    return tex;
  }, [colors.floorColor]);

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
      <planeGeometry args={[FLOOR_SIZE, FLOOR_SIZE]} />
      <meshStandardMaterial
        map={gridHelper}
        metalness={0.1}
        roughness={0.9}
      />
    </mesh>
  );
}

function RoomLabel({
  obj,
  preset,
}: {
  obj: DetectedObject;
  preset: FinishPreset;
}) {
  const colors = FINISH_PRESETS[preset];
  const pos = resolvePosition(obj);

  return (
    <Text
      position={[pos.x, pos.y + 0.2, pos.z]}
      fontSize={0.5}
      color={colors.accentColor}
      anchorX="center"
      anchorY="middle"
      fontWeight="bold"
    >
      {obj.label || 'Room'}
    </Text>
  );
}

function SceneContent({
  parsed,
  preset,
  materialTextures,
  onObjectClick,
}: {
  parsed: ParsedObjects;
  preset: FinishPreset;
  materialTextures?: Record<string, string>;
  onObjectClick?: (obj: DetectedObject) => void;
}) {
  const hasContent =
    parsed.walls.length > 0 ||
    parsed.partitions.length > 0 ||
    parsed.doors.length > 0 ||
    parsed.windows.length > 0 ||
    parsed.furniture.length > 0;

  return (
    <>
      {/* Lights */}
      <ambientLight intensity={0.5} />
      <directionalLight position={[15, 20, 10]} intensity={1.2} castShadow />
      <directionalLight position={[-10, 5, -10]} intensity={0.3} />
      <hemisphereLight
        args={['#ffffff', '#444444']}
        intensity={0.4}
      />

      {/* Floor always present */}
      <FloorMesh preset={preset} />

      {hasContent ? (
        <>
          {/* Walls */}
          {parsed.walls.map((obj) => (
            <WallMesh
              key={obj.id}
              obj={obj}
              preset={preset}
              textureUrl={materialTextures?.wall}
              onClick={onObjectClick}
            />
          ))}

          {/* Partitions */}
          {parsed.partitions.map((obj) => {
            const colors = FINISH_PRESETS[preset];
            const dim = resolveDimensions(obj);
            const length = safeDim(dim.length, 3);
            const height = safeDim(dim.height, 2.5);
            const thickness = safeDim(dim.thickness, 0.1);
            const pos = resolvePosition(obj);
            const rot = resolveRotation3d(obj);

            return (
              <mesh
                key={obj.id}
                position={[pos.x, pos.y, pos.z]}
                rotation={[rot.x, rot.y, rot.z]}
                onClick={(e) => {
                  e.stopPropagation();
                  onObjectClick?.(obj);
                }}
              >
                <boxGeometry args={[length, height, thickness]} />
                <meshStandardMaterial
                  color={colors.wallColor}
                  transparent
                  opacity={0.7}
                  metalness={colors.metalness}
                  roughness={colors.roughness}
                />
              </mesh>
            );
          })}

          {/* Doors */}
          {parsed.doors.map((obj) => (
            <DoorMesh
              key={obj.id}
              obj={obj}
              preset={preset}
              onClick={onObjectClick}
            />
          ))}

          {/* Windows */}
          {parsed.windows.map((obj) => (
            <WindowMesh
              key={obj.id}
              obj={obj}
              preset={preset}
              onClick={onObjectClick}
            />
          ))}

          {/* Furniture */}
          {parsed.furniture.map((obj) => (
            <FurnitureMesh
              key={obj.id}
              obj={obj}
              preset={preset}
              onClick={onObjectClick}
            />
          ))}

          {/* Room labels */}
          {parsed.rooms.map((obj) => (
            <RoomLabel key={obj.id} obj={obj} preset={preset} />
          ))}

          {/* Other objects as labels */}
          {parsed.others.map((obj) => (
            <RoomLabel key={obj.id} obj={obj} preset={preset} />
          ))}
        </>
      ) : (
        <Text
          position={[0, 2, 0]}
          fontSize={0.6}
          color="#888888"
          anchorX="center"
          anchorY="middle"
        >
          No objects to display
        </Text>
      )}
    </>
  );
}

export default function ThreeViewer({
  objects,
  onObjectClick,
  finishPreset = 'modern',
  materialTextures,
}: ThreeViewerProps) {
  const parsed = useMemo(() => parseObjects(objects), [objects]);

  return (
    <Canvas
      camera={{
        position: [8, 6, 8],
        fov: 45,
        near: 0.1,
        far: 100,
      }}
      style={{ background: '#1a1a1a', borderRadius: '8px' }}
      gl={{ antialias: true }}
      shadows
    >
      <SceneContent
        parsed={parsed}
        preset={finishPreset}
        materialTextures={materialTextures}
        onObjectClick={onObjectClick}
      />
      <OrbitControls
        autoRotate
        autoRotateSpeed={1}
        enableDamping
        dampingFactor={0.1}
        minDistance={2}
        maxDistance={30}
      />
    </Canvas>
  );
}
