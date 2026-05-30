// SEO + JSON-LD constants for the field-notes + fieldkit homepages.
// SITE.url is the canonical destination at ainative.business since that is
// where this content publishes. The repo URL points back to this source.

export const SITE = {
  name: 'ainative',
  url: 'https://ainative.business',
  description:
    'Field notes on building AI-native businesses — agent orchestration, governed inference, RAG patterns, training economics, and the deep-dive papers that anchor the AI Native Platform series. By Manav Sehgal.',
  logo: 'https://ainative.business/ainative-s-128.png',
  ogImage: 'https://ainative.business/og-image.png',
  themeColor: '#0f172a',
  license: 'Apache-2.0',
};

export const ORGANIZATION = {
  '@type': 'Organization',
  name: 'ainative',
  url: SITE.url,
  logo: SITE.logo,
  description: SITE.description,
  founder: {
    '@type': 'Person',
    name: 'Manav Sehgal',
  },
  foundingDate: '2026',
  sameAs: [
    'https://github.com/manavsehgal/ai-field-notes',
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
