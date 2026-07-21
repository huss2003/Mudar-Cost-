import { Title, Text, Badge, Container } from '@mantine/core';

export default function Costs() {
  return (
    <Container size="lg" py="xl">
      <Badge size="lg" color="lime" mb="md">Module</Badge>
      <Title order={1}>Costs</Title>
      <Text c="dimmed" mt="sm">
        Calculate and analyze project costs. Apply pricing rules, labor rates,
        and overhead to generate detailed cost estimates and reports.
      </Text>
      <Badge mt="lg" variant="outline" color="gray">Coming Soon</Badge>
    </Container>
  );
}
