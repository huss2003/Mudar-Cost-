import { Title, Text, Badge, Container } from '@mantine/core';

export default function AI() {
  return (
    <Container size="lg" py="xl">
      <Badge size="lg" color="violet" mb="md">Module</Badge>
      <Title order={1}>AI Assistant</Title>
      <Text c="dimmed" mt="sm">
        Leverage AI-powered tools for automatic quantity extraction, cost
        predictions, and intelligent project recommendations.
      </Text>
      <Badge mt="lg" variant="outline" color="gray">Coming Soon</Badge>
    </Container>
  );
}
