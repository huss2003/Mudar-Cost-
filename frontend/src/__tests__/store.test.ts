/**
 * Vitest tests for the Zustand stores:
 * - useProjectStore (projectStore.ts)
 * - useAuthStore (auth.ts)
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';

// ── Auth Store ─────────────────────────────────────────────────────────

describe('useAuthStore', () => {
  beforeEach(() => {
    // Clear module state between tests
    vi.resetModules();
    // Clear localStorage
    localStorage.clear();
  });

  it('should initialise with default values (no auth)', async () => {
    const { useAuthStore } = await import('../store/auth');
    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.refreshToken).toBeNull();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isInitialized).toBe(false);
  });

  it('should update state on login()', async () => {
    const { useAuthStore } = await import('../store/auth');
    const user = {
      sub: 'abc123',
      email: 'test@example.com',
      name: 'Test User',
      roles: ['admin'],
    };

    useAuthStore.getState().login('my-access-token', 'my-refresh-token', user);

    const state = useAuthStore.getState();
    expect(state.token).toBe('my-access-token');
    expect(state.refreshToken).toBe('my-refresh-token');
    expect(state.user).toEqual(user);
    expect(state.isAuthenticated).toBe(true);
  });

  it('should clear state on logout()', async () => {
    const { useAuthStore } = await import('../store/auth');
    // Login first
    useAuthStore.getState().login('token', 'refresh', {
      sub: 'abc', email: 'a@b.com', name: 'A', roles: [],
    });
    expect(useAuthStore.getState().isAuthenticated).toBe(true);

    // Logout
    useAuthStore.getState().logout();
    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.refreshToken).toBeNull();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it('should update tokens via setTokens()', async () => {
    const { useAuthStore } = await import('../store/auth');
    useAuthStore.getState().setTokens('new-token', 'new-refresh');
    const state = useAuthStore.getState();
    expect(state.token).toBe('new-token');
    expect(state.refreshToken).toBe('new-refresh');
  });

  it('should set initialized', async () => {
    const { useAuthStore } = await import('../store/auth');
    expect(useAuthStore.getState().isInitialized).toBe(false);
    useAuthStore.getState().setInitialized();
    expect(useAuthStore.getState().isInitialized).toBe(true);
  });

  it('should build loginUrl', async () => {
    const { useAuthStore } = await import('../store/auth');
    const state = useAuthStore.getState();
    expect(state.loginUrl).toContain('openid-connect/auth');
    expect(state.loginUrl).toContain('response_type=code');
  });
});

// ── Project Store ──────────────────────────────────────────────────────

describe('useProjectStore', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('should initialise with default project state', async () => {
    const { useProjectStore } = await import('../store/projectStore');
    const state = useProjectStore.getState();
    expect(state.currentProjectId).toBeNull();
    expect(state.detectedObjects).toEqual([]);
    expect(state.boqItems).toEqual([]);
    expect(state.selectedObjectId).toBeNull();
    expect(state.selectedObject).toBeNull();
    expect(state.materialOptions).toEqual([]);
    expect(state.selectedMaterialId).toBeNull();
    expect(state.projectTotal).toBe(0);
    expect(state.finishPreset).toBe('modern');
    expect(state.viewMode).toBe('split');
    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
  });

  it('should set current project via setCurrentProject()', async () => {
    const { useProjectStore } = await import('../store/projectStore');
    // Mock disconnectSSE and connectSSE to avoid EventSource errors
    const store = useProjectStore.getState();
    vi.spyOn(store, 'disconnectSSE').mockImplementation(() => {});
    vi.spyOn(store, 'connectSSE').mockImplementation(() => {});

    useProjectStore.getState().setCurrentProject(42);

    const state = useProjectStore.getState();
    expect(state.currentProjectId).toBe(42);
    expect(state.detectedObjects).toEqual([]);
    expect(state.boqItems).toEqual([]);
    expect(state.selectedObjectId).toBeNull();
    expect(state.selectedMaterialId).toBeNull();
    expect(state.projectTotal).toBe(0);
  });

  it('should set detected objects', async () => {
    const { useProjectStore } = await import('../store/projectStore');
    const objects = [
      { id: 1, drawing_id: 1, object_type: 'wall', label: 'Wall-A',
        length: 5000, width: null, area: 15, height: 3000, thickness: null,
        location_x: null, location_y: null, layer: 'A-WALL', confidence: 0.95,
        bbox_coords: null },
    ];
    useProjectStore.getState().setDetectedObjects(objects);
    expect(useProjectStore.getState().detectedObjects).toEqual(objects);
  });

  it('should select object and update selectedObject', async () => {
    const { useProjectStore } = await import('../store/projectStore');
    const objects = [
      { id: 1, drawing_id: 1, object_type: 'door', label: 'Door-1',
        length: 900, width: null, area: null, height: 2100, thickness: null,
        location_x: null, location_y: null, layer: 'A-DOOR', confidence: 0.9,
        bbox_coords: null },
    ];
    useProjectStore.getState().setDetectedObjects(objects);
    useProjectStore.getState().selectObject(1);

    const state = useProjectStore.getState();
    expect(state.selectedObjectId).toBe(1);
    expect(state.selectedObject).toEqual(objects[0]);
    expect(state.materialOptions).toEqual([]);
    expect(state.selectedMaterialId).toBeNull();
  });

  it('should deselect object', async () => {
    const { useProjectStore } = await import('../store/projectStore');
    useProjectStore.getState().selectObject(null);
    const state = useProjectStore.getState();
    expect(state.selectedObjectId).toBeNull();
    expect(state.selectedObject).toBeNull();
  });

  it('should set material options', async () => {
    const { useProjectStore } = await import('../store/projectStore');
    const options = [
      { material_id: 1, name: 'Tile A', brand: 'Kajaria', sku: 'T-1',
        rate: 850, unit: 'sqm', gst_rate: 18, vendor_name: 'Acme',
        lead_time_days: 7, warranty: null, fire_rating: null, is_preferred: true },
    ];
    useProjectStore.getState().setMaterialOptions(options);
    expect(useProjectStore.getState().materialOptions).toEqual(options);
  });

  it('should call API on selectMaterial and update store', async () => {
    const { useProjectStore } = await import('../store/projectStore');

    // Set up initial state
    useProjectStore.getState().setDetectedObjects([
      { id: 1, drawing_id: 1, object_type: 'wall', label: 'Wall',
        length: 5000, width: null, area: 15, height: 3000, thickness: null,
        location_x: null, location_y: null, layer: 'A-WALL', confidence: 0.95,
        bbox_coords: null },
    ]);
    useProjectStore.getState().selectObject(1);

    // Mock the client module
    vi.doMock('../api/client', () => {
      return {
        default: {
          post: vi.fn().mockResolvedValue({ data: {} }),
          get: vi.fn().mockResolvedValue({
            data: [
              { material_id: 1, name: 'Tile A', brand: 'Kajaria', sku: 'T-1',
                rate: 850, unit: 'sqm', gst_rate: 18, vendor_name: 'Acme',
                lead_time_days: 7, warranty: null, fire_rating: null, is_preferred: true },
            ],
          }),
        },
      };
    });

    // Re-import to pick up the mock
    const mod = await import('../store/projectStore');

    // No BOQ items - should set error
    await mod.useProjectStore.getState().selectMaterial(1);

    const state = mod.useProjectStore.getState();
    expect(state.error).toContain('No BOQ item');
  });

  it('should set finish preset', async () => {
    const { useProjectStore } = await import('../store/projectStore');
    useProjectStore.getState().setFinishPreset('luxury');
    expect(useProjectStore.getState().finishPreset).toBe('luxury');
  });

  it('should ignore invalid finish preset', async () => {
    const { useProjectStore } = await import('../store/projectStore');
    useProjectStore.getState().setFinishPreset('invalid');
    expect(useProjectStore.getState().finishPreset).toBe('modern');
  });

  it('should set view mode', async () => {
    const { useProjectStore } = await import('../store/projectStore');
    useProjectStore.getState().setViewMode('3d');
    expect(useProjectStore.getState().viewMode).toBe('3d');
  });

  it('should ignore invalid view mode', async () => {
    const { useProjectStore } = await import('../store/projectStore');
    useProjectStore.getState().setViewMode('4d');
    expect(useProjectStore.getState().viewMode).toBe('split');
  });

  it('should set BOQ items', async () => {
    const { useProjectStore } = await import('../store/projectStore');
    const items = [
      { id: 1, description: 'Tile floor', quantity: 100, unit: 'sqm',
        rate: 850, total: 85000, trade: 'Flooring', material_name: null },
    ];
    useProjectStore.getState().setBoqItems(items);
    expect(useProjectStore.getState().boqItems).toEqual(items);
  });

  it('should set project total', async () => {
    const { useProjectStore } = await import('../store/projectStore');
    useProjectStore.getState().setProjectTotal(22331.46);
    expect(useProjectStore.getState().projectTotal).toBe(22331.46);
  });

  it('should connect and disconnect SSE', async () => {
    const { useProjectStore } = await import('../store/projectStore');
    // connectSSE should instantiate EventSource
    expect(() => {
      useProjectStore.getState().connectSSE(1);
    }).not.toThrow();

    // disconnectSSE should close it
    expect(() => {
      useProjectStore.getState().disconnectSSE();
    }).not.toThrow();
  });
});
