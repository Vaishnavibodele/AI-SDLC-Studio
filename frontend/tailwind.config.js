/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        darkBg: '#0b0f19',
        darkPanel: '#111827',
        accentPrimary: '#6366f1',  // Indigo
        accentSecondary: '#8b5cf6', // Purple
        accentSuccess: '#10b981',   // Emerald
      }
    },
  },
  plugins: [],
}
