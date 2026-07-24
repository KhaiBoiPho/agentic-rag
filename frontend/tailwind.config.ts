import type { Config } from 'tailwindcss';

// ChatGPT-style monochrome palette: near-black accent/buttons, neutral grays
// for surfaces/borders, dedicated dark tones for the sidebar rail.
const config: Config = {
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f7f7f8',
          100: '#ececf1',
          200: '#d9d9e3',
          300: '#c5c5d2',
          400: '#8e8ea0',
          500: '#40414f',
          600: '#0d0d0d', // primary button / accent (near-black)
          700: '#000000',
          800: '#000000',
          900: '#000000',
        },
        ink: {
          DEFAULT: '#0d0d0d',
          secondary: '#353740',
          mute: '#6e6e80',
        },
        canvas: {
          DEFAULT: '#ffffff',
          soft: '#f7f7f8',
        },
        hairline: {
          DEFAULT: '#e5e5e5',
          input: '#d9d9e3',
        },
        sidebar: {
          DEFAULT: '#171717',
          hover: '#212121',
          active: '#212121',
          border: '#2a2a2a',
          text: '#ececec',
          mute: '#8e8ea0',
        },
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', '-apple-system', 'sans-serif'],
      },
      borderRadius: {
        pill: '9999px',
      },
    },
  },
  plugins: [],
};

export default config;
