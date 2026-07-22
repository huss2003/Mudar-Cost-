import { AppShell, NavLink, Title, Group } from '@mantine/core';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  IconComponents,
  IconRulerMeasure,
  IconBuildingStore,
  IconCurrencyDollar,
  IconBrain,
  IconFileExport,
} from '@tabler/icons-react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Sphere, MeshDistortMaterial } from '@react-three/drei';

const navItems = [
  { label: 'Drawings', path: '/drawings', icon: IconComponents },
  { label: 'Quantities', path: '/quantities', icon: IconRulerMeasure },
  { label: 'Materials', path: '/materials', icon: IconBuildingStore },
  { label: 'Costs', path: '/costs', icon: IconCurrencyDollar },
  { label: 'AI', path: '/ai', icon: IconBrain },
  { label: 'Exports', path: '/exports', icon: IconFileExport },
];

function ThreeBackground() {
  return (
    <div style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', zIndex: -1, opacity: 0.08 }}>
      <Canvas camera={{ position: [0, 0, 5], fov: 45 }}>
        <ambientLight intensity={0.5} />
        <directionalLight position={[10, 10, 5]} intensity={1} />
        <Sphere args={[1.5, 64, 64]} position={[0, 0, 0]}>
          <MeshDistortMaterial
            color="#228be6"
            attach="material"
            distort={0.3}
            speed={2}
            roughness={0.2}
            metalness={0.8}
          />
        </Sphere>
        <OrbitControls enableZoom={false} autoRotate autoRotateSpeed={1.5} />
      </Canvas>
    </div>
  );
}

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <AppShell
      navbar={{ width: 260, breakpoint: 'sm' }}
      header={{ height: 60 }}
      padding="md"
    >
      <ThreeBackground />
      <AppShell.Header>
        <Group h="100%" px="md">
          <IconComponents size={28} color="#228be6" />
          <Title order={4}>Auto Cost Engine</Title>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        <AppShell.Section grow>
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              label={item.label}
              leftSection={<item.icon size={20} />}
              active={location.pathname === item.path}
              onClick={() => navigate(item.path)}
              variant="light"
              mb={4}
            />
          ))}
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
