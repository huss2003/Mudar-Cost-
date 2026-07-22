import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Text,
  Badge,
  Card,
  Group,
  Stack,
  Title,
  Box,
  TextInput,
  ActionIcon,
  Loader,
  Paper,
  Divider,
  Avatar,
} from '@mantine/core';
import {
  IconBrain,
  IconSend,
  IconSparkles,
  IconBulb,
  IconCurrencyDollar,
  IconLayoutBoard,
  IconTool,
} from '@tabler/icons-react';
import supabase from '../api/supabase';

/* ─── Types ──────────────────────────────────────────────────── */
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
}

/* ─── Suggestion chips ───────────────────────────────────────── */
const SUGGESTIONS = [
  { icon: IconCurrencyDollar, text: 'What is the total project cost?', color: '#2dd4a8' },
  { icon: IconLayoutBoard, text: 'List all BOQ items by category', color: '#5e6ad2' },
  { icon: IconBulb, text: 'Suggest cost-saving alternatives', color: '#f97316' },
  { icon: IconTool, text: 'Which materials have the longest lead time?', color: '#a78bfa' },
];

/* ─── Format currency ────────────────────────────────────────── */
const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value);

/* ─── AI response generator (local intelligence) ─────────────── */
async function generateAIResponse(
  query: string,
): Promise<string> {
  const q = query.toLowerCase();

  try {
    // Try to answer from Supabase data
    if (q.includes('total') && (q.includes('cost') || q.includes('price') || q.includes('project'))) {
      const { data } = await supabase.from('boq_items').select('total');
      const total = (data || []).reduce((sum: number, item: any) => sum + (item.total || 0), 0);
      return `The current **total project cost** is **${formatCurrency(total)}** based on ${data?.length || 0} BOQ items.\n\nYou can view a detailed breakdown in the **Costs** page.`;
    }

    if (q.includes('material') && q.includes('lead')) {
      const { data } = await supabase.from('materials').select('name, brand, lead_time_days').order('lead_time_days', { ascending: false }).limit(5);
      if (data && data.length > 0) {
        const list = data.map((m: any) => `• **${m.name}** (${m.brand}) — ${m.lead_time_days} days`).join('\n');
        return `Here are the materials with the **longest lead times**:\n\n${list}\n\nConsider ordering these early to avoid project delays.`;
      }
      return 'I don\'t have materials data available yet. Upload materials in the **Materials** page first.';
    }

    if (q.includes('category') || q.includes('boq') || q.includes('trade')) {
      const { data } = await supabase.from('boq_items').select('trade, total');
      if (data && data.length > 0) {
        const tradeMap = new Map<string, number>();
        for (const item of data) {
          const trade = (item as any).trade || 'General';
          tradeMap.set(trade, (tradeMap.get(trade) || 0) + ((item as any).total || 0));
        }
        const sorted = Array.from(tradeMap.entries()).sort((a, b) => b[1] - a[1]);
        const list = sorted.map(([trade, total]) => `• **${trade}**: ${formatCurrency(total)}`).join('\n');
        return `Here's the **BOQ breakdown by trade**:\n\n${list}`;
      }
      return 'No BOQ items found yet. Upload a drawing in the **Drawings** page to generate quantities.';
    }

    if (q.includes('save') || q.includes('cost') || q.includes('alternativ') || q.includes('cheaper')) {
      const { data } = await supabase.from('boq_items').select('description, total, rate').order('total', { ascending: false }).limit(3);
      if (data && data.length > 0) {
        const items = data.map((item: any) => `• **${item.description}** — ${formatCurrency(item.total)} (rate: ${formatCurrency(item.rate)})`).join('\n');
        return `Here are the **highest-cost items** where savings might be found:\n\n${items}\n\n💡 **Suggestions:**\n• Consider bulk purchasing discounts\n• Compare with alternative materials in the **Materials** page\n• Check for seasonal pricing variations`;
      }
      return 'I need BOQ data to provide cost-saving suggestions. Upload a drawing first!';
    }

    if (q.includes('drawing') || q.includes('uploaded')) {
      const { count } = await supabase.from('drawings').select('id', { count: 'exact', head: true });
      return `You currently have **${count || 0} drawings** uploaded.\n\nUpload more drawings in the **Drawings** page for AI analysis, or view existing drawings to see detected objects.`;
    }

    if (q.includes('hello') || q.includes('hi') || q.includes('hey') || q.includes('help')) {
      return `Hello! 👋 I'm your **AI Construction Cost Assistant**.\n\nI can help you with:\n• 📊 Project cost summaries\n• 🏗️ BOQ breakdowns by trade\n• 💡 Cost-saving recommendations\n• 📦 Material lead time analysis\n• 📐 Drawing inventory\n\nJust ask me anything about your project!`;
    }

    // Fallback with context
    return `I understand you're asking about: *"${query}"*\n\nI can provide specific answers about:\n• **Project costs** — total budget, per-item breakdown\n• **Materials** — pricing, lead times, alternatives\n• **BOQ data** — organized by trade/category\n• **Drawings** — inventory and status\n\nTry asking a more specific question like "What is the total project cost?" or "Which materials have the longest lead time?"`;
  } catch {
    return 'I encountered an issue accessing project data. Please make sure the database is connected and try again.';
  }
}

/* ─── Auto-scroll hook ───────────────────────────────────────── */
function useAutoScroll(dependency: any) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: 'smooth' });
  }, [dependency]);
  return ref;
}

/* ════════════════════════════════════════════════════════════════ */
/*  MAIN COMPONENT                                                */
/* ════════════════════════════════════════════════════════════════ */

export default function AI() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: `Hello! I'm your **AI Construction Cost Assistant**. 🧠\n\nAsk me anything about your project — costs, materials, BOQ analysis, or optimization suggestions.`,
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useAutoScroll(messages);

  /* ── Send message ─────────────────────────────────────────── */
  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || loading) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await generateAIResponse(text);
      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: 'system',
          content: 'Sorry, I encountered an error. Please try again.',
          timestamp: new Date(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [loading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleSuggestion = (text: string) => {
    sendMessage(text);
  };

  return (
    <Box p="lg" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* ══════ HEADER ══════ */}
      <Group justify="space-between" mb="lg" wrap="wrap" gap="sm" className="ace-animate-in">
        <div>
          <Group gap="xs" mb={4}>
            <Badge size="sm" variant="light" color="violet" leftSection={<IconBrain size={12} />}>
              Module
            </Badge>
          </Group>
          <Title order={2} fw={700} style={{ letterSpacing: '-0.02em' }}>
            <span className="ace-gradient-text">AI Assistant</span>
          </Title>
          <Text size="sm" c="dimmed" mt={2}>
            Get intelligent insights on costs, materials, and optimization
          </Text>
        </div>
      </Group>

      {/* ══════ CHAT AREA ══════ */}
      <Paper
        p={0}
        style={{
          flex: 1,
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Messages */}
        <div
          ref={scrollRef}
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '16px',
          }}
        >
          <Stack gap="md" style={{ maxWidth: 720, margin: '0 auto' }}>
            {messages.map((msg) => (
              <Group
                key={msg.id}
                gap="sm"
                align="flex-start"
                justify={msg.role === 'user' ? 'flex-end' : 'flex-start'}
                className="ace-animate-in"
              >
                {msg.role !== 'user' && (
                  <Avatar
                    size={32}
                    radius="md"
                    style={{
                      background: 'linear-gradient(135deg, #5e6ad2, #a78bfa)',
                      flexShrink: 0,
                    }}
                  >
                    <IconSparkles size={16} />
                  </Avatar>
                )}
                <Box
                  p="sm"
                  px="md"
                  style={{
                    maxWidth: '80%',
                    borderRadius: msg.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                    background: msg.role === 'user'
                      ? 'linear-gradient(135deg, #5e6ad2, #4d58b0)'
                      : 'var(--ace-bg-elevated)',
                    border: msg.role === 'user' ? 'none' : '1px solid var(--ace-border)',
                  }}
                >
                  <Text
                    size="sm"
                    style={{
                      whiteSpace: 'pre-wrap',
                      lineHeight: 1.6,
                      color: msg.role === 'user' ? '#fff' : 'var(--ace-text)',
                    }}
                    dangerouslySetInnerHTML={{
                      __html: msg.content
                        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                        .replace(/\*(.*?)\*/g, '<em>$1</em>')
                        .replace(/\n/g, '<br/>'),
                    }}
                  />
                </Box>
                {msg.role === 'user' && (
                  <Avatar
                    size={32}
                    radius="md"
                    style={{
                      background: 'rgba(255,255,255,0.08)',
                      flexShrink: 0,
                      fontWeight: 600,
                      fontSize: 12,
                    }}
                  >
                    DU
                  </Avatar>
                )}
              </Group>
            ))}
            {loading && (
              <Group gap="sm" align="flex-start" className="ace-animate-in">
                <Avatar
                  size={32}
                  radius="md"
                  style={{ background: 'linear-gradient(135deg, #5e6ad2, #a78bfa)', flexShrink: 0 }}
                >
                  <IconSparkles size={16} />
                </Avatar>
                <Box
                  p="sm"
                  px="md"
                  style={{
                    borderRadius: '12px 12px 12px 2px',
                    background: 'var(--ace-bg-elevated)',
                    border: '1px solid var(--ace-border)',
                  }}
                >
                  <Group gap="xs">
                    <Loader size={14} color="accent" />
                    <Text size="sm" c="dimmed">Thinking...</Text>
                  </Group>
                </Box>
              </Group>
            )}
          </Stack>
        </div>

        <Divider style={{ borderColor: 'var(--ace-border)' }} />

        {/* ══════ SUGGESTIONS ══════ */}
        {messages.length <= 2 && (
          <Box px="md" pt="sm" style={{ maxWidth: 720, margin: '0 auto', width: '100%' }}>
            <Text size="xs" c="dimmed" mb="xs">Quick actions:</Text>
            <Group gap="xs" mb="sm" wrap="wrap">
              {SUGGESTIONS.map((s, idx) => (
                <Card
                  key={idx}
                  p="xs"
                  px="sm"
                  className="ace-btn ace-animate-in"
                  style={{
                    animationDelay: `${idx * 60}ms`,
                    cursor: 'pointer',
                    flexShrink: 0,
                  }}
                  onClick={() => handleSuggestion(s.text)}
                >
                  <Group gap={4} wrap="nowrap">
                    <s.icon size={12} style={{ color: s.color }} />
                    <Text size="xs">{s.text}</Text>
                  </Group>
                </Card>
              ))}
            </Group>
          </Box>
        )}

        {/* ══════ INPUT ══════ */}
        <Box p="md" style={{ maxWidth: 720, margin: '0 auto', width: '100%' }}>
          <form onSubmit={handleSubmit}>
            <Group gap="sm">
              <TextInput
                placeholder="Ask about costs, materials, or your project..."
                value={input}
                onChange={(e) => setInput(e.currentTarget.value)}
                style={{ flex: 1 }}
                size="md"
                variant="filled"
                disabled={loading}
                rightSection={
                  <ActionIcon
                    type="submit"
                    variant="subtle"
                    color="accent"
                    disabled={!input.trim() || loading}
                    className="ace-btn"
                  >
                    <IconSend size={18} />
                  </ActionIcon>
                }
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e);
                  }
                }}
              />
            </Group>
          </form>
        </Box>
      </Paper>
    </Box>
  );
}
