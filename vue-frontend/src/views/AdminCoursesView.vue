<template>
  <div class="admin-page">
    <el-breadcrumb separator="/" class="breadcrumb">
      <el-breadcrumb-item>高校课程AI学习助手平台</el-breadcrumb-item>
      <el-breadcrumb-item>课程管理</el-breadcrumb-item>
    </el-breadcrumb>

    <h1 class="page-title">课程管理</h1>
    <p class="page-desc">查看全平台课程与规模数据；「进入课程」可查看该课程的知识库、问答分析与课程看板（只读，不修改课程内容）。删除课程会同时清理该课程的文档、向量、入库任务、问答记录与学习历史。</p>

    <div class="toolbar">
      <div class="summary">
        <span class="summary-num">{{ courses.length }}</span>
        <span class="summary-label">门课程</span>
      </div>
      <div class="toolbar-actions">
        <el-input v-model="keyword" placeholder="搜索课程名 / 教师" clearable style="width: 220px" />
        <el-button :loading="loading" @click="loadCourses">刷新列表</el-button>
      </div>
    </div>

    <el-empty v-if="!loading && !filteredCourses.length" description="暂无课程" />

    <el-card v-else class="panel-card table-card">
      <el-table :data="filteredCourses" stripe style="width:100%">
        <el-table-column label="课程名称" min-width="200">
          <template #default="{ row }">
            <div class="course-name">{{ row.course_name }}</div>
            <div class="course-desc" :title="row.description">{{ row.description || '暂无课程说明' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="授课教师" width="140">
          <template #default="{ row }">{{ row.owner_username || '-' }}</template>
        </el-table-column>
        <el-table-column prop="member_count" label="成员" width="80" />
        <el-table-column prop="document_count" label="文档" width="80" />
        <el-table-column prop="qa_count" label="问答" width="80" />
        <el-table-column label="引用率" width="100">
          <template #default="{ row }">{{ Math.round((row.citation_rate || 0) * 100) }}%</template>
        </el-table-column>
        <el-table-column label="课程码" width="130">
          <template #default="{ row }"><span class="invite-code">{{ row.invite_code }}</span></template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="enterCourse(row)">进入课程</el-button>
            <el-button size="small" type="danger" plain @click="removeCourse(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi } from '../api'
import { errorMessage } from '../api/request'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const courses = ref([])
const keyword = ref('')
const loading = ref(false)

const filteredCourses = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return courses.value
  return courses.value.filter((course) =>
    `${course.course_name} ${course.owner_username || ''}`.toLowerCase().includes(key)
  )
})

function formatTime(value) {
  if (!value) return '-'
  let text = String(value)
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text)) {
    text = text.replace(' ', 'T') + 'Z'
  }
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? text : date.toLocaleString('zh-CN', { hour12: false })
}

async function loadCourses() {
  loading.value = true
  try {
    const { data } = await adminApi.listCourses()
    courses.value = data.courses || []
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    loading.value = false
  }
}

// 管理员进入课程：以只读视角切换当前课程，与「我的课程」选择课程等价
function enterCourse(row) {
  auth.setCourse({
    course_id: row.course_id,
    course_name: row.course_name,
    role_in_course: 'admin'
  })
  ElMessage.success(`已进入课程：${row.course_name}`)
  router.push('/dashboard')
}

async function removeCourse(row) {
  try {
    await ElMessageBox.confirm(
      `删除「${row.course_name}」会同时清理课程的文档、向量、任务、问答记录与学习历史，且无法恢复。确定删除吗？`,
      '删除课程',
      { type: 'error', confirmButtonText: '确定删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    const { data } = await adminApi.deleteCourse(row.course_id)
    ElMessage.success(`课程已删除，清理文档 ${data.removed_documents ?? 0} 个`)
    await loadCourses()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

onMounted(loadCourses)
</script>

<style scoped>
.admin-page { max-width: 1180px; margin: 0 auto; }
.breadcrumb { margin-bottom: 18px; }
.breadcrumb :deep(.el-breadcrumb__inner) { color: var(--muted); font-weight: 500; font-size: 12px; }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--text); flex-wrap: wrap; }
.toolbar-actions { display: flex; align-items: center; gap: 10px; }
.summary { display: flex; align-items: baseline; gap: 8px; }
.summary-num { font-size: 30px; font-weight: 900; color: var(--text); line-height: 1; }
.summary-label { color: var(--muted); font-size: 13px; }
.course-name { color: var(--text); font-weight: 600; }
.course-desc { color: var(--muted); font-size: 12px; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 340px; }
.invite-code { color: var(--primary); letter-spacing: .08em; font-weight: 600; }
.table-card { margin-top: 14px; }
@media (max-width: 768px) {
  .admin-page { max-width: 100%; margin: 0; }
  .toolbar-actions { width: 100%; }
  .toolbar-actions :deep(.el-input) { flex: 1; width: auto !important; }
  .course-desc { max-width: 220px; }
}
</style>
