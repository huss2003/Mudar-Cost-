import { Title, Text, Badge, Container } from '@mantine/core';

export default function Exports() {
  return (
    <Container size="lg" py="xl">
      <Badge size="lg" color="orange" mb="md">Module</Badge>
      <Title order={1}>Exports</Title>
      <Text c="dimmed" mt="sm">
        Export cost estimates, quantity takeoffs, and reports in various
        formats including PDF, Excel, CSV, and industry-standard formats.
      </Text>
      <Badge mt="lg" variant="outline" color="gray">Coming Soon</Badge>
    </Container>
  );
}
