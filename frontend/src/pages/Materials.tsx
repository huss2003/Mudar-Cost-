import { Title, Text, Badge, Container } from '@mantine/core';

export default function Materials() {
  return (
    <Container size="lg" py="xl">
      <Badge size="lg" color="teal" mb="md">Module</Badge>
      <Title order={1}>Materials</Title>
      <Text c="dimmed" mt="sm">
        Browse and manage material catalogs, pricing data, and supplier
        information. Configure material databases used in cost estimation.
      </Text>
      <Badge mt="lg" variant="outline" color="gray">Coming Soon</Badge>
    </Container>
  );
}
