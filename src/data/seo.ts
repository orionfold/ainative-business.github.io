export const SITE = {
  name: 'ainative',
  url: 'https://ainative.business',
  description:
    'AI Native Business — the book and companion software from Orionfold, an AI studio building open software, custom models, and local-first playbooks that run privately on your own machine.',
  logo: 'https://ainative.business/ainative-s-128.png',
  ogImage: 'https://ainative.business/og-image.png',
  ogImageAlt:
    'AI Native Business — book and companion software from Orionfold. Open source, local-first, free.',
  themeColor: '#0f172a',
  themeColorLight: '#ffffff',
  license: 'Apache-2.0',
  twitter: '@manavsehgal',
};

// Author identity. The richer the sameAs links, the easier it is for answer
// engines (Perplexity, ChatGPT, Google AI Overviews) to recognize the author
// as a single entity across the web and cite the site with confidence.
export const PERSON = {
  '@type': 'Person',
  name: 'Manav Sehgal',
  url: `${SITE.url}/about/`,
  image: SITE.logo,
  jobTitle: 'Founder, Orionfold',
  description:
    'Founder of Orionfold, an AI studio folding the frontier down to one desk. Author of AI Native Business. 25-year arc across Xerox PARC, HCL, Daily Mail, Amazon AGI, and AWS.',
  knowsAbout: [
    'AI-native businesses',
    'Autonomous business systems',
    'AI agent orchestration',
    'Large language models',
    'Agentic systems governance',
    'Local-first software',
    'Multi-agent coordination',
    'Retrieval-augmented generation',
    'Small language models',
    'GPU economics',
  ],
  alumniOf: [
    { '@type': 'EducationalOrganization', name: 'Harvard Business School Online' },
    { '@type': 'EducationalOrganization', name: 'MIT Sloan' },
    { '@type': 'EducationalOrganization', name: 'UC Berkeley Haas School of Business' },
  ],
  sameAs: [
    'https://orionfold.com',
    'https://github.com/manavsehgal',
    'https://x.com/manavsehgal',
    'https://www.linkedin.com/in/manavsehgal/',
    'https://www.kaggle.com/manavsehgal',
  ],
};

export const ORGANIZATION = {
  '@type': 'Organization',
  name: 'Orionfold',
  legalName: 'Orionfold LLC',
  url: 'https://orionfold.com',
  logo: SITE.logo,
  description:
    'Orionfold is an AI studio folding the frontier down to one desk — open software, custom models, and playbooks that run privately on your own machine.',
  founder: PERSON,
  foundingDate: '2026',
  sameAs: [
    'https://orionfold.com',
    'https://github.com/manavsehgal',
    'https://x.com/manavsehgal',
  ],
};

export const PUBLISHER = {
  '@type': 'Organization',
  name: 'Orionfold',
  legalName: 'Orionfold LLC',
  url: 'https://orionfold.com',
  logo: {
    '@type': 'ImageObject',
    url: SITE.logo,
  },
};
