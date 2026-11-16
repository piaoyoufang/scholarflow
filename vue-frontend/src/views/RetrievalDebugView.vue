<template>
  <div>
    <h1 class="page-title">检索可视化</h1>
    <p class="page-desc">教师可查看检索召回和排序过程，定位知识库命中效果。</p>
    <div v-if="!auth.hasCourse" class="empty-state">请先选择课程。</div>
    <template v-else>
      <el-card class="panel-card">
        <el-input v-model="query" placeholder="例如：RAG 的核心流程是什么？" />
        <el-button type="primary" :loading="loading" @click="debug">查看召回结果</el-button>
      </el-card>
      <el-card v-if="result" class="panel-card">
        <div v-if="!rows.length" class="empty-state">没有召回任何片段，请先确认课程资料已入库。</div>
        <el-table v-else :data="rows" stripe style="width: 100%">
          <el-table-column prop="rank" label="排名" width="80" />
          <el-table-column prop="score" label="相关性分数" width="140" />
          <el-table-column prop="source_name" label="来源文件" min-width="180" show-overflow-tooltip />
          <el-table-column prop="chunk_index" label="片段序号" width="110" />
          <el-table-column prop="content_preview" label="内容预览" min-width="320" show-overflow-tooltip />
        </el-table>
      </el-card>
    </template>
  </div>
</template>
<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { courseApi } from '../api'
import { errorMessage } from '../api/request'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const query = ref('')
const loading = ref(false)
const result = ref(null)
const rows = computed(() => result.value?.items || [])

async function debug() {
  if (!query.value.trim()) return ElMessage.error('检索问题不能为空')
  loading.value = true
  try {
    const { data } = await courseApi.retrievalDebug(auth.currentCourseId, {
      question: query.value.trim(),
      thread_id: auth.threadId
    })
    result.value = data
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    loading.value = false
  }
}
</script>
<style scoped>
.panel-card { margin-bottom: 18px; }
.el-input { margin-bottom: 12px; }
</style>
