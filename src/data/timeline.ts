export type ProjectStatus = 'completed' | 'active';

export interface TechCategory {
  label: string;
  items: string[];
}

export interface TimelineItem {
  year: string;
  project: string;
  role: string;
  description: string;
  achievements: string[];
  stats: string;
  techWave: string;
  techCategories: TechCategory[];
  status: ProjectStatus;
  isCurrent: boolean;
  accentToken: string;
  domainIcon: string;
}

export const metrics = [
  { label: 'Lines of Code', target: 345, suffix: 'K+' },
  { label: 'AI Agents', target: 56, suffix: '+' },
  { label: 'Production Systems', target: 8, suffix: '' },
  { label: 'Projects', target: 18, suffix: '+' },
  { label: 'Blog Articles', target: 68, suffix: '+' },
];

export const timeline: TimelineItem[] = [
  {
    year: '2024',
    project: 'FinEdge',
    role: 'Fintech investment intelligence',
    description:
      'Built a financial intelligence platform that uses LLMs to analyze market data, generate investment insights, and automate portfolio reporting. Integrated Anthropic APIs with PostgreSQL for persistent knowledge storage.',
    achievements: [
      'Automated daily market analysis across 500+ equities',
      'Reduced investment research time by 80% with AI-generated briefs',
      'Built custom LangGraph pipelines for multi-step financial reasoning',
    ],
    stats: '45K LOC · Python + Anthropic + PostgreSQL',
    techWave: 'LLM APIs',
    techCategories: [
      { label: 'Backend', items: ['Python', 'PostgreSQL', 'FastAPI'] },
      { label: 'AI', items: ['Anthropic', 'LangGraph', 'RAG'] },
    ],
    status: 'completed',
    isCurrent: false,
    accentToken: '--svg-accent-green',
    domainIcon: 'chart-line',
  },
  {
    year: '2024',
    project: 'SuperCRM',
    role: 'Agentic social CRM',
    description:
      'Developed an AI-powered CRM that uses Claude agents to enrich contacts, draft personalized outreach, and manage social relationships. Pioneered early agent-framework patterns with structured tool use.',
    achievements: [
      'Managed 10K+ contacts with AI-enriched profiles',
      'Automated outreach generation with context-aware personalization',
      'Integrated multi-channel social data into unified contact graph',
    ],
    stats: '35.7K LOC · Next.js + Claude AI Agents',
    techWave: 'Agent Frameworks',
    techCategories: [
      { label: 'Frontend', items: ['Next.js', 'React', 'Tailwind'] },
      { label: 'AI', items: ['Claude', 'Tool Use', 'Embeddings'] },
      { label: 'Backend', items: ['TypeScript', 'Prisma'] },
    ],
    status: 'completed',
    isCurrent: false,
    accentToken: '--svg-accent-orange',
    domainIcon: 'users',
  },
  {
    year: '2025',
    project: 'KnowledgeGraph',
    role: 'Strategic intelligence & benchmarks',
    description:
      'Created a knowledge management platform with interactive D3.js visualizations for mapping research domains, benchmarking AI models, and surfacing strategic insights from large document corpora.',
    achievements: [
      'Visualized 2,000+ interconnected research nodes with D3.js force graphs',
      'Built interactive benchmark dashboards for AI model comparison',
      'Processed 500+ research papers into structured knowledge graphs',
    ],
    stats: '81.7K LOC · Next.js + D3.js + React',
    techWave: 'RAG Systems',
    techCategories: [
      { label: 'Frontend', items: ['Next.js', 'React', 'D3.js'] },
      { label: 'Backend', items: ['MDX', 'Node.js'] },
      { label: 'AI', items: ['RAG', 'Embeddings', 'Vector Search'] },
    ],
    status: 'completed',
    isCurrent: false,
    accentToken: '--svg-accent-purple',
    domainIcon: 'network',
  },
  {
    year: '2025',
    project: 'AgentKit',
    role: 'Visual agent testing platform',
    description:
      'Designed a desktop application for visually building, testing, and debugging AI agent workflows. Used Tauri for native performance with a React frontend and Pydantic-validated agent schemas.',
    achievements: [
      'Created visual drag-and-drop agent workflow builder',
      'Achieved 473 tests with comprehensive agent behavior coverage',
      'Implemented MCP protocol support for standardized agent communication',
    ],
    stats: '473 tests · React + TypeScript + Tauri',
    techWave: 'MCP Protocol',
    techCategories: [
      { label: 'Frontend', items: ['React', 'TypeScript'] },
      { label: 'Infrastructure', items: ['Tauri', 'Rust'] },
      { label: 'AI', items: ['Pydantic', 'MCP', 'Agent Schemas'] },
    ],
    status: 'completed',
    isCurrent: false,
    accentToken: '--svg-accent-teal',
    domainIcon: 'puzzle',
  },
  {
    year: '2025',
    project: 'Canvas OS',
    role: 'Analytics & data visualization',
    description:
      'Built an interactive canvas-based analytics platform with React Flow for node-based data pipelines and Zustand for performant state management. Focused on real-time data visualization and exploration.',
    achievements: [
      'Rendered complex data pipelines with 100+ connected nodes',
      'Built real-time analytics dashboards with sub-100ms updates',
      'Designed extensible plugin system for custom visualization widgets',
    ],
    stats: '28.4K LOC · React + TypeScript',
    techWave: 'Agent Orchestration',
    techCategories: [
      { label: 'Frontend', items: ['React', 'TypeScript', 'React Flow'] },
      { label: 'Infrastructure', items: ['Zustand', 'Vite'] },
    ],
    status: 'completed',
    isCurrent: false,
    accentToken: '--svg-accent-pink',
    domainIcon: 'layout',
  },
  {
    year: '2025',
    project: 'DeepResearch',
    role: 'Grounded AI research assistant',
    description:
      'Developed an autonomous research agent that breaks complex questions into sub-queries, searches multiple sources, synthesizes findings, and generates cited research reports with LangGraph orchestration.',
    achievements: [
      'Generated 36 research blueprints with full source citations',
      'Implemented multi-hop reasoning across diverse knowledge sources',
      'Built Vue-based interface for interactive research exploration',
    ],
    stats: '36 blueprints · Python + LangGraph + Vue',
    techWave: 'Autonomous Agents',
    techCategories: [
      { label: 'Frontend', items: ['Vue', 'TypeScript'] },
      { label: 'Backend', items: ['Python', 'FastAPI'] },
      { label: 'AI', items: ['LangGraph', 'RAG', 'Multi-hop Reasoning'] },
    ],
    status: 'completed',
    isCurrent: false,
    accentToken: '--svg-accent-blue',
    domainIcon: 'search',
  },
  {
    year: '2025',
    project: 'BrowseAI',
    role: 'AI browsing companion',
    description:
      'Created a browser extension that brings AI assistance directly into the browsing experience. Supports multiple LLM providers (Anthropic, OpenAI, Gemini) for page summarization, Q&A, and content extraction.',
    achievements: [
      'Shipped cross-browser extension with 3 LLM provider integrations',
      'Built intelligent page context extraction for grounded responses',
      'Implemented streaming responses with real-time markdown rendering',
    ],
    stats: '21.9K LOC · Browser extension + multi-provider LLM',
    techWave: 'AI Interfaces',
    techCategories: [
      { label: 'Frontend', items: ['Browser Extension', 'TypeScript'] },
      { label: 'AI', items: ['Anthropic', 'OpenAI', 'Gemini'] },
    ],
    status: 'completed',
    isCurrent: false,
    accentToken: '--svg-accent-cyan',
    domainIcon: 'globe',
  },
  {
    year: '2025',
    project: 'TerminalOS',
    role: 'CLI workflow automation',
    description:
      'Built a terminal-native AI assistant that orchestrates CLI workflows across multiple LLM providers. Supports Anthropic, OpenAI, Gemini, and local Ollama models with unified command interface.',
    achievements: [
      'Unified 4 LLM providers under a single CLI interface',
      'Automated complex multi-step terminal workflows',
      'Implemented local-first model support via Ollama integration',
    ],
    stats: '15K LOC · Anthropic + OpenAI + Gemini + Ollama',
    techWave: 'AI Form Factors',
    techCategories: [
      { label: 'Backend', items: ['TypeScript', 'Node.js'] },
      { label: 'AI', items: ['Anthropic', 'OpenAI', 'Gemini', 'Ollama'] },
    ],
    status: 'completed',
    isCurrent: false,
    accentToken: '--svg-accent-red',
    domainIcon: 'terminal',
  },
  {
    year: '2026',
    project: 'ainative',
    role: 'The book and the companion software',
    description:
      'Shipped a local-first AI business operating system that orchestrates agents across your entire company — with 6-runtime execution, smart routing, governance, cost controls, chat UI, multi-channel delivery (Slack/Telegram), 37 workflow patterns, 45+ database tables, and a living book documenting the journey. 100% free community edition — no tiers, no telemetry.',
    achievements: [
      'Shipped 148 features across 38 operator surfaces in 37 days — open source, local-first, 100% free',
      '6-runtime architecture with smart router, 56+ agent profiles, and 37 workflow patterns',
      'Full chat system, heartbeat scheduling, multi-channel delivery, and human-in-the-loop governance',
    ],
    stats: '127K LOC · 810 tests · 148/198 features shipped',
    techWave: 'The Harness Layer',
    techCategories: [
      { label: 'Frontend', items: ['Next.js 16', 'React 19', 'Tailwind v4', 'shadcn/ui'] },
      { label: 'Backend', items: ['TypeScript', 'SQLite', 'Drizzle ORM'] },
      { label: 'AI', items: ['Claude Agent SDK', 'Codex', 'Anthropic Direct', 'OpenAI Direct', 'Ollama'] },
      { label: 'Infrastructure', items: ['Vitest', 'Turbopack', 'SSE', 'E2E Tests'] },
    ],
    status: 'active',
    isCurrent: true,
    accentToken: '--color-primary',
    domainIcon: 'shield',
  },
];
