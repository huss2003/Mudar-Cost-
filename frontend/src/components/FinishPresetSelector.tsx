import { SegmentedControl, Group, Text } from '@mantine/core';
import type { FinishPreset } from '../types';
import { FINISH_PRESETS } from '../types';

interface FinishPresetSelectorProps {
  value: FinishPreset;
  onChange: (value: FinishPreset) => void;
}

const PRESET_LABELS: Record<FinishPreset, string> = {
  modern: 'Modern',
  industrial: 'Industrial',
  luxury: 'Luxury',
  minimal: 'Minimal',
};

export default function FinishPresetSelector({
  value,
  onChange,
}: FinishPresetSelectorProps) {
  const data = (Object.keys(FINISH_PRESETS) as FinishPreset[]).map((key) => {
    const colors = FINISH_PRESETS[key];
    return {
      value: key,
      label: (
        <Group gap="xs" wrap="nowrap">
          {/* Color swatches: wall color + accent color */}
          <Group gap={2} wrap="nowrap">
            <div
              style={{
                width: 12,
                height: 12,
                borderRadius: '2px',
                backgroundColor: colors.wallColor,
                border: '1px solid rgba(255,255,255,0.2)',
              }}
            />
            <div
              style={{
                width: 12,
                height: 12,
                borderRadius: '2px',
                backgroundColor: colors.accentColor,
                border: '1px solid rgba(255,255,255,0.2)',
              }}
            />
          </Group>
          <Text size="sm">{PRESET_LABELS[key]}</Text>
        </Group>
      ),
    };
  });

  return (
    <SegmentedControl
      value={value}
      onChange={(val) => onChange(val as FinishPreset)}
      data={data}
      size="sm"
      fullWidth
    />
  );
}
