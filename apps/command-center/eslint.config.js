import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

const files = ['**/*.{ts,tsx}']

export default tseslint.config(
  { ignores: ['dist'] },
  { ...js.configs.recommended, files },
  ...tseslint.configs.recommended.map(config => ({ ...config, files })),
  { ...reactHooks.configs.flat.recommended, files },
  { ...reactRefresh.configs.vite, files },
  { files, languageOptions: { ecmaVersion: 2022, globals: globals.browser } },
)
