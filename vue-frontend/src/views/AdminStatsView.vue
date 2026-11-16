<template>
  <div class="admin-page">
    <el-breadcrumb separator="/" class="breadcrumb">
      <el-breadcrumb-item>高校课程AI学习助手平台</el-breadcrumb-item>
      <el-breadcrumb-item>数据统计</el-breadcrumb-item>
    </el-breadcrumb>

    <div class="page-head">
      <div>
        <h1 class="page-title">数据统计</h1>
        <p class="page-desc">全平台账号、课程、知识库与问答质量总览，帮助管理员掌握系统整体运行情况。</p>
      </div>
      <el-button :loading="loading" @click="loadStats">刷新数据</el-button>
    </div>

    <div class="stat-grid">
      <el-card class="stat-card">
        <div class="stat-label">账号总数</div>
        <div class="stat-value">{{ stats.users.total }}</div>
        <div class="stat-foot">
          教师 {{ stats.users.teacher }} ／ 学生 {{ stats.users.student }} ／ 禁用 {{ stats.users.disabled }}
        </div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">课程总数</div>
        <div class="stat-value">{{ stats.courses.total }}</div>
        <div class="stat-foot">选课关系 {{ stats.courses.enrollments }} 条</div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">知识库文档</div>
        <div class="stat-value">{{ stats.documents.document_count }}</div>
        <div class="stat-foot">
          成功 {{ stats.documents.success_document_count }} ／ 失败 {{ stats.documents.failed_document_count }} ／ 处理中 {{ stats.documents.processing_document_count }}
        </div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">问答总量</div>
        <div class="stat-value">{{ stats.qa.qa_count }}</div>
        <div class="stat-foot">
          引用率 {{ percent(stats.qa.citation_rate) }} ／ 无引用 {{ stats.qa.no_citation_count }} ／ 低质量 {{ stats.qa.low_quality_count }}
        </div>
      </el-card>
      <el-card class="stat-card">
        <div class="stat-label">问答反馈</div>
        <div class="stat-value">{{ stats.feedback.up + stats.feedback.down }}</div>
        <div class="stat-foot">好评 {{ stats.feedback.up }} ／ 差评 {{ stats.feedback.down }}</div>
      </el-card>
    </div>

    <div class="toolbar">
      <h2>课程数据</h2>
      <span class="toolbar-tip">按问答量排序</span>
    </div>

    <el-empty v-if="!loading && !stats.course_rows.length" description="暂无课程数据" />

    <el-card v-else class="panel-card table-card">
      <el-table :data="stats.course_rows" stripe style="width:100%">
        <el-table-column prop="course_name" label="课程名称" min-width="200" />
        <el-table-column label="授课教师" width="140">
          <template #default="{ row }">{{ row.owner_username || '-' }}</template>
        </el-table-column>
        <el-table-column prop="member_count" label="成员" width="80" />
        <el-table-column prop="document_count" label="文档" width="80" />
        <el-table-column prop="qa_count" label="问答" width="80" />
        <el-table-column label="引用率" width="100">
          <template #default="{ row }">{{ percent(row.citation_rate) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="toolbar second">
      <h2>高频问题</h2>
      <span class="toolbar-tip">全平台提问次数 Top 10</span>
    </div>

    <el-empty v-if="!loading && !stats.top_questions.length" description="暂无问答数据" />

    <el-card v-else class="panel-card table-card">
      <el-table :data="stats.top_questions" stripe style="width:100%">
        <el-table-column type="index" label="#" width="60" />
        <el-table-column prop="question" label="问题" min-width="420" show-overflow-tooltip />
        <el-table-column prop="count" label="提问次数" width="120" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminApi } from '../api'
import { errorMessage } from '../api/request'

const loading = ref(false)
const stats = reactive({
  users: { total: 0, teacher: 0, student: 0, disabled: 0 },
  courses: { total: 0, enrollments: 0 },
  documents: { document_count: 0, success_document_count: 0, failed_document_count: 0, processing_document_count: 0 },
  qa: { qa_count: 0, no_citation_count: 0, low_quality_count: 0, citation_rate: 0 },
  feedback: { up: 0, down: 0 },
  course_rows: [],
  top_questions: []
})

function percent(value) {
  return `${Math.round((value || 0) * 100)}%`
}

async function loadStats() {
  loading.value = true
  try {
    const { data } = await adminApi.stats()
    Object.assign(stats, data)
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    loading.value = false
  }
}

onMounted(loadStats)
</script>

<style scoped>
.admin-page { max-width: 1180px; margin: 0 auto; }
.breadcrumb { margin-bottom: 18px; }
.breadcrumb :deep(.el-breadcrumb__inner) { color: var(--muted); font-weight: 500; font-size: 12px; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin: 20px 0 8px; }
.stat-card { min-height: 140px; }
.stat-label { color: var(--muted); font-size: 13px; font-weight: 500; }
.stat-value { color: var(--text); font-size: 34px; font-weight: 900; line-height: 1.2; margin: 8px 0 6px; letter-spacing: -.02em; }
.stat-foot { color: var(--muted); font-size: 12px; line-height: 1.6; }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--text); margin-top: 20px; }
.toolbar.second { margin-top: 26px; }
.toolbar h2 { margin: 0; font-size: 20px; font-weight: 900; }
.toolbar-tip { color: var(--muted); font-size: 12px; }
.table-card { margin-top: 12px; }
@media (max-width: 768px) {
  .admin-page { max-width: 100%; margin: 0; }
  .stat-grid { grid-template-columns: 1fr 1fr; gap: 10px; }
  .stat-card { min-height: 120px; }
  .stat-value { font-size: 26px; }
  .toolbar h2 { font-size: 18px; }
}
</style>
