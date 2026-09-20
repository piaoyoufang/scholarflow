<template>
  <!-- v-html 渲染的是 markdown-it 输出（html: false 已禁用原生 HTML 注入），XSS 风险已由解析器侧控制 -->
  <!-- eslint-disable-next-line vue/no-v-html -->
  <div class="markdown-body" v-html="html"></div>
</template>

<script setup>
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'

const props = defineProps({
  source: {
    type: String,
    default: ''
  }
})

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  breaks: true
})

const html = computed(() => md.render(props.source || ''))
</script>
