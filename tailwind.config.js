/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#142033',
        accent: '#3157d5',
        violet: '#7059d9',
      },
      fontFamily: {
        sans: ['"Microsoft YaHei"', '"微软雅黑"', '"Noto Sans SC"', '"Microsoft JhengHei"', 'Arial', 'sans-serif'],
        mono: ['"Microsoft YaHei"', '"微软雅黑"', '"Noto Sans SC"', '"Microsoft JhengHei"', 'Arial', 'sans-serif'],
      },
      boxShadow: { soft: '0 20px 60px -30px rgba(26, 45, 90, .28)' },
    },
  },
  plugins: [],
};
