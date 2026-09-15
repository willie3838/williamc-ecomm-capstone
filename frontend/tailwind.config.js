/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bb: {
          blue: '#0046be',
          'blue-dark': '#001e73',
          'blue-light': '#0058f0',
          yellow: '#fff000',
          'yellow-hover': '#ffe000',
          slate: '#1d252c',
          gray: '#55555a',
          light: '#f4f6f8',
        }
      },
      keyframes: {
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.5s infinite',
      },
    },
  },
  plugins: [],
};
