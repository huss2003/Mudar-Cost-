import { useEffect, useState } from 'react';
import {
  AppShell,
  NavLink,
  Group,
  Text,
  Box,
  Stack,
  Badge,
  Avatar,
  Tooltip,
  Divider,
  ScrollArea,
} from '@mantine/core';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  IconComponents,
  IconRulerMeasure,
  IconBuildingStore,
  IconCurrencyDollar,
  IconBrain,
  IconFileExport,
  IconLayoutDashboard,
  IconChevronRight,
} from '@tabler/icons-react';
import supabase from '../api/supabase';

const navItems = [
  { label: 'Drawings', path: '/drawings', icon: IconComponents, color: '#38bdf8' },
  { label: 'Quantities', path: '/quantities', icon: IconRulerMeasure, color: '#a78bfa' },
  { label: 'Materials', path: '/materials', icon: IconBuildingStore, color: '#f97316' },
  { label: 'Costs', path: '/costs', icon: IconCurrencyDollar, color: '#2dd4a8' },
  { label: 'AI', path: '/ai', icon: IconBrain, color: '#c084fc' },
  { label: 'Exports', path: '/exports', icon: IconFileExport, color: '#fb923c' },
];

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [projectCount, setProjectCount] = useState(0);

  useEffect(() => {
    async function fetchProjects() {
      const { data } = await supabase.from('projects').select('id', { count: 'exact', head: true });
      if (data !== null) setProjectCount(projectCount);
    }
    fetchProjects();
  }, []);

  return (
    <AppShell
      navbar={{ width: 260, breakpoint: 'sm' }}
      header={{ height: 56 }}
      padding={0}
    >
      {/* ══════ HEADER ══════ */}
      <AppShell.Header style={{ zIndex: 100 }}>
        <Group h="100%" px="lg" justify="space-between">
          <Group gap="sm">
            <Box
              style={{
                width: 32,
                height: 32,
                borderRadius: '10px',
                background: 'linear-gradient(135deg, #5e6ad2, #a78bfa)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 0 20px rgba(94,106,210,0.3)',
              }}
            >
              <IconLayoutDashboard size={18} color="white" />
            </Box>
            <div>
              <Text fw={700} size="sm" style={{ lineHeight: 1.2, letterSpacing: '-0.01em' }}>
                Auto Cost Engine
              </Text>
              <Text size="xs" c="dimmed" style={{ lineHeight: 1.2 }}>
                Construction Estimation Platform
              </Text>
            </div>
          </Group>

          <Group gap="md">
            <Badge
              variant="light"
              color="green"
              size="sm"
              leftSection={
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#2dd4a8', display: 'inline-block' }} />
              }
            >
              {projectCount} projects
            </Badge>
            <Tooltip label="Demo User">
              <Avatar
                size={30}
                radius="md"
                style={{
                  background: 'linear-gradient(135deg, #5e6ad2, #a78bfa)',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: 12,
                }}
              >
                DU
              </Avatar>
            </Tooltip>
          </Group>
        </Group>
      </AppShell.Header>

      {/* ══════ SIDEBAR ══════ */}
      <AppShell.Navbar style={{ overflow: 'hidden' }}>
        <Stack h="100%" gap={0}>
          {/* Nav items */}
          <ScrollArea style={{ flex: 1 }} offsetScrollbars>
            <Box px="sm" pt="md" pb="sm">
              <Text
                size="xs"
                fw={600}
                c="dimmed"
                tt="uppercase"
                style={{ letterSpacing: '0.08em', padding: '0 12px', marginBottom: 8 }}
              >
                Navigation
              </Text>

              <Stack gap={2}>
                {navItems.map((item, index) => {
                  const isActive = location.pathname === item.path;
                  return (
                    <Box
                      key={item.path}
                      className="ace-animate-slide"
                      style={{ animationDelay: `${index * 50}ms` }}
                    >
                      <NavLink
                        label={
                          <Group gap="xs" justify="space-between" wrap="nowrap">
                            <Text size="sm">{item.label}</Text>
                            {isActive && (
                              <IconChevronRight size={14} style={{ color: item.color, opacity: 0.6 }} />
                            )}
                          </Group>
                        }
                        leftSection={
                          <Box
                            style={{
                              width: 28,
                              height: 28,
                              borderRadius: '8px',
                              background: isActive ? `${item.color}18` : 'rgba(255,255,255,0.03)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              transition: 'all 200ms ease',
                            }}
                          >
                            <item.icon
                              size={16}
                              style={{
                                color: isActive ? item.color : '#5c5e68',
                                transition: 'color 200ms ease',
                              }}
                            />
                          </Box>
                        }
                        active={isActive}
                        onClick={() => navigate(item.path)}
                        variant="subtle"
                        style={{
                          borderRadius: '10px',
                          padding: '8px 12px',
                          height: 'auto',
                        }}
                      />
                    </Box>
                  );
                })}
              </Stack>
            </Box>
          </ScrollArea>

          {/* Bottom section */}
          <Box p="sm">
            <Divider mb="sm" style={{ borderColor: 'rgba(255,255,255,0.06)' }} />
            <Box
              p="sm"
              style={{
                borderRadius: '12px',
                background: 'linear-gradient(135deg, rgba(94,106,210,0.08), rgba(167,139,250,0.05))',
                border: '1px solid rgba(94,106,210,0.12)',
              }}
            >
              <Group gap="xs">
                <Box
                  style={{
                    width: 24,
                    height: 24,
                    borderRadius: '6px',
                    background: 'linear-gradient(135deg, #5e6ad2, #a78bfa)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <IconBrain size={12} color="white" />
                </Box>
                <div>
                  <Text size="xs" fw={600} style={{ lineHeight: 1.2 }}>AI Assistant</Text>
                  <Text size="xs" c="dimmed" style={{ lineHeight: 1.2 }}>Ready to help</Text>
                </div>
              </Group>
            </Box>
          </Box>
        </Stack>
      </AppShell.Navbar>

      {/* ══════ MAIN CONTENT ══════ */}
      <AppShell.Main style={{ background: 'var(--ace-bg)', overflow: 'auto' }}>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
