import type { Config } from 'tailwindcss';

// Palette derived from frontend/DESIGN.md (Stripe-inspired) — indigo primary +
// deep-navy ink, mapped onto the brand-* scale so existing bg-brand-*/text-brand-*
// usages across components pick up the new identity without a full rename.
const config: Config = {
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef0ff',
          100: '#e0e3fe',
          200: '#b9b9f9', // primary-bg-subdued-hover
          300: '#9d97fb',
          400: '#8079fc',
          500: '#665efd', // primary-soft
          600: '#533afd', // primary
          700: '#4434d4', // primary-deep
          800: '#2e2b8c', // primary-press
          900: '#1c1e54', // brand-dark-900
        },
        ink: {
          DEFAULT: '#0d253d',
          secondary: '#273951',
          mute: '#64748d',
        },
        canvas: {
          DEFAULT: '#ffffff',
          soft: '#f6f9fc',
          cream: '#f5e9d4',
        },
        hairline: {
          DEFAULT: '#e3e8ee',
          input: '#a8c3de',
        },
        ruby: '#ea2261',
        magenta: '#f96bee',
      },
      fontFamily: {
        sans: [
          'var(--font-inter)',
          'SF Pro Display',
          'system-ui',
          '-apple-system',
          'sans-serif',
        ],
      },
      borderRadius: {
        pill: '9999px',
      },
    },
  },
  plugins: [],
};

export default config;
