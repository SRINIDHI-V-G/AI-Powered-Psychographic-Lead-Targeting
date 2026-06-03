/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'ocean-o': '#6366f1',
        'ocean-c': '#0891b2',
        'ocean-e': '#f59e0b',
        'ocean-a': '#10b981',
        'ocean-n': '#ef4444',
        'platform-instagram': '#e1306c',
        'platform-reddit': '#ff4500',
        'platform-twitter': '#1da1f2',
        'platform-mock': '#94a3b8',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
