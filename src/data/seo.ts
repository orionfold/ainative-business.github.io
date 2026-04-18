export const SITE = {
  name: 'ainative',
  url: 'https://ainative.business',
  description:
    'AI Native Business — the book and the companion software. A personal research project by Manav Sehgal into building AI-native businesses. Open source, local-first, and free.',
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
