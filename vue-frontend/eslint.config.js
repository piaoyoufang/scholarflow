import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import prettier from 'eslint-config-prettier' // 只负责关闭与 Prettier 冲突的格式规则，各司其职

export default [
  js.configs.recommended, // JS 基础规则（未定义变量、不可达代码等）
  ...pluginVue.configs['flat/recommended'], // Vue3 官方推荐规则（template 语法、props 校验等）
  prettier, // 格式交给 Prettier，ESLint 只管代码质量
  {
    languageOptions: {
      globals: {
        // 浏览器环境全局变量，不声明会报 no-undef
        window: 'readonly',
        document: 'readonly',
        localStorage: 'readonly',
        fetch: 'readonly',
        AbortController: 'readonly',
        console: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        URL: 'readonly',
        Blob: 'readonly',
        File: 'readonly',
        FormData: 'readonly',
        TextDecoderStream: 'readonly',
        CustomEvent: 'readonly',
        Event: 'readonly',
        navigator: 'readonly',
        location: 'readonly',
        alert: 'readonly',
        confirm: 'readonly'
      }
    }
  },
  {
    files: ['**/*.test.js'],
    languageOptions: {
      globals: {
        // Vitest 单测环境：测试文件显式 import describe/it/expect，这里只需 stub 相关的全局
        globalThis: 'readonly'
      }
    }
  }
]
