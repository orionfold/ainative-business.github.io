export const SITE = {
  name: 'ainative',
  url: 'https://ainative.business',
  description:
    'AI Native Business — the book and the companion software. A personal research project by Manav Sehgal into building AI-native businesses. Open source, local-first, and free.',
  logo: 'https://ainative.business/ainative-s-128.png',
  ogImage: 'https://ainative.business/og-image.png',
  ogImageAlt:
    'AI Native Business — book and companion software by Manav Sehgal. Open source, local-first, free.',
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
  jobTitle: 'Solutions Leader, AWS Frontier AI',
  description:
    'Author of AI Native Business. Solutions Leader at AWS Frontier AI. 25-year arc across Xerox PARC, HCL, Daily Mail, Amazon AGI, and AWS.',
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
    'https://github.com/manavsehgal',
    'https://x.com/manavsehgal',
    'https://www.linkedin.com/in/manavsehgal/',
    'https://www.kaggle.com/manavsehgal',
  ],
};

export const ORGANIZATION = {
  '@type': 'Organization',
  name: 'ainative',
  url: SITE.url,
  logo: SITE.logo,
  description: SITE.description,
  founder: PERSON,
  foundingDate: '2026',
  sameAs: [
    'https://github.com/manavsehgal/ainative',
    'https://x.com/manavsehgal',
  ],
};

export const PUBLISHER = {
  '@type': 'Organization',
  name: SITE.name,
  url: SITE.url,
  logo: {
    '@type': 'ImageObject',
    url: SITE.logo,
  },
};
