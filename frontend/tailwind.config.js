/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      typography: {
        invert: {
          css: {
            color: '#e2e8f0',
            'h1,h2,h3,h4': { color: '#f1f5f9' },
            strong: { color: '#f1f5f9' },
            code: { color: '#93c5fd' },
            a: { color: '#60a5fa' },
          },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
