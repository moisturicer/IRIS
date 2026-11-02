import js from '@eslint/js';
import tseslint from '@typescript-eslint/eslint-plugin';
import reactHooks from 'eslint-plugin-react-hooks';

export default [
  { ignores: ['dist/**'] },
  js.configs.recommended,
  ...tseslint.configs['flat/recommended'],
  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs['recommended-latest'].rules,
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/**/*.test.{ts,tsx}', 'src/test/**'],
    rules: {
      // IR-207: inspect literals and template segments, including conditional
      // classes and hover/responsive variants. Borders and rings remain legal.
      'no-restricted-syntax': ['error',
        {
          selector: 'Literal[value=/(text|bg)-gold/]',
          message: 'Gold is decoration only; use a readable IRIS text or fill token (IR-207).',
        },
        {
          selector: 'TemplateElement[value.raw=/(text|bg)-gold/]',
          message: 'Gold is decoration only; use a readable IRIS text or fill token (IR-207).',
        },
      ],
    },
  },
];
