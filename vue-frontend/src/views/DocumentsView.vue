<template>
  <div>
    <h1 class="page-title">课程知识库</h1>
    <p class="page-desc">上传课程资料，后台自动解析、切块并写入课程知识库。</p>

    <div v-if="!auth.hasCourse" class="empty-state">请先在“我的课程”里创建或选择一门课程。</div>

    <template v-else>
      <el-card class="panel-card upload-card">
        <template #header>
          <div class="card-header">
            <span>上传课程资料</span>
            <el-tag effect="plain" round>PDF / TXT / Markdown</el-tag>
          </div>
        </template>
        <el-upload drag :auto-upload="false" :limit="1" :on-change="onFileChange" :on-remove="onRemove" accept=".pdf,.txt,.md">
          <div class="upload-text">拖拽 PDF / TXT / Markdown 到这里，或点击选择文件</div>
          <div class="upload-hint">上传后系统会自动完成解析、切片和向量入库。</div>
        </el-upload>
        <el-button type="primary" :disabled="!file" :loading="uploading" @click="upload">上传并入库</el-button>
      </el-card>

      <el-card class="panel-card task-card">
        <template #header>
          <div class="card-header">
            <div>
              <span>资料处理进度</span>
              <p>展示最近的资料解析和入库状态，系统会自动刷新处理中任务。</p>
            </div>
            <el-button :loading="taskLoading" @click="refreshAll">刷新</el-button>
          </div>
        </template>

        <div v-if="!tasks.length" class="empty-state task-empty">暂无处理记录。上传资料后这里会显示解析进度。</div>
        <div v-else class="task-list">
          <div v-for="task in recentTasks" :key="task.task_id" class="task-item">
            <div class="task-main">
              <div class="task-title">
                <span>{{ taskDocumentName(task) }}</span>
                <el-tag :type="taskTagType(task.status)" effect="light" round>{{ taskStatusText(task.status) }}</el-tag>
              </div>
              <p>{{ task.message || task.error || '系统正在处理课程资料' }}</p>
              <el-progress :percentage="Number(task.progress || 0)" :status="progressStatus(task.status)" :stroke-width="10" />
            </div>
            <div class="task-time">
              <span>更新时间</span>
              <b>{{ formatTime(task.updated_at || task.created_at) }}</b>
            </div>
          </div>
        </div>
      </el-card>

      <div class="toolbar">
        <h2>当前课程文档列表</h2>
        <el-button :loading="documentLoading" @click="refreshAll">刷新</el-button>
      </div>

      <div v-if="!documents.length" class="empty-state">这门课程暂时没有入库文档。请先上传课程资料。</div>

      <div v-else class="grid grid-2">
        <el-card v-for="doc in documents" :key="doc.source_id" class="doc-card">
          <div class="doc-top">
            <h3>{{ doc.original_name }}</h3>
            <el-tag :type="doc.status === 'success' ? 'success' : 'warning'" effect="light" round>{{ documentStatusText(doc.status) }}</el-tag>
          </div>
          <p>类型：{{ doc.file_type || '未知' }} ｜ 切片：{{ doc.chunk_count || 0 }}</p>
          <div class="actions">
            <el-button @click="reingest(doc)">重新入库</el-button>
            <el-button type="danger" plain @click="remove(doc)">删除资料</el-button>
          </div>
        </el-card>
      </div>

      <el-card v-if="documents.length" class="panel-card table-card">
        <el-table :data="documents" stripe style="width:100%">
          <el-table-column prop="original_name" label="文件名称" min-width="220" show-overflow-tooltip />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="row.status === 'success' ? 'success' : 'warning'" effect="light" round>{{ documentStatusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="file_type" label="类型" width="100" />
          <el-table-column prop="chunk_count" label="切片数" width="100" />
          <el-table-column prop="created_at" label="上传时间" min-width="180" show-overflow-tooltip />
        </el-table>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { courseApi } from '../api'
import { errorMessage } from '../api/request'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const documents = ref([])
const tasks = ref([])
const file = ref(null)
const uploading = ref(false)
const documentLoading = ref(false)
const taskLoading = ref(false)
let pollTimer = null

const recentTasks = computed(() => tasks.value.slice(0, 5))

function onFileChange(uploadFile) {
  file.value = uploadFile.raw
}

function onRemove() {
  file.value = null
}

function isRunning(status) {
  return ['pending', 'processing', 'running'].includes(String(status || '').toLowerCase())
}

function taskStatusText(status) {
  const map = {
    pending: '等待处理',
    processing: '处理中',
    running: '处理中',
    success: '入库成功',
    completed: '入库成功',
    failed: '入库失败',
    error: '入库失败'
  }
  return map[String(status || '').toLowerCase()] || '未知状态'
}

function taskTagType(status) {
  const value = String(status || '').toLowerCase()
  if (['success', 'completed'].includes(value)) return 'success'
  if (['failed', 'error'].includes(value)) return 'danger'
  return 'warning'
}

function progressStatus(status) {
  const value = String(status || '').toLowerCase()
  if (['success', 'completed'].includes(value)) return 'success'
  if (['failed', 'error'].includes(value)) return 'exception'
  return undefined
}

function documentStatusText(status) {
  const map = {
    success: '已入库',
    processing: '处理中',
    pending: '等待处理',
    failed: '入库失败',
    error: '入库失败'
  }
  return map[String(status || '').toLowerCase()] || status || '未知'
}

function formatTime(value) {
  if (!value) return '暂无'
  return String(value).replace('T', ' ').replace(/\.\d+.*/, '').replace('+00:00', '')
}

function taskDocumentName(task) {
  const doc = documents.value.find((item) => item.source_id === task.source_id)
  return doc?.original_name || task.result?.filename || '课程资料处理任务'
}

function updatePolling() {
  const shouldPoll = tasks.value.some((task) => isRunning(task.status))
  if (shouldPoll && !pollTimer) {
    pollTimer = window.setInterval(refreshAll, 3000)
  }
  if (!shouldPoll && pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function loadDocuments() {
  if (!auth.currentCourseId) return
  documentLoading.value = true
  try {
    const { data } = await courseApi.documents(auth.currentCourseId)
    documents.value = data.documents || []
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    documentLoading.value = false
  }
}

async function loadTasks() {
  if (!auth.currentCourseId) return
  taskLoading.value = true
  try {
    const { data } = await courseApi.tasks(auth.currentCourseId)
    tasks.value = data.tasks || []
    updatePolling()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    taskLoading.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadDocuments(), loadTasks()])
}

async function upload() {
  uploading.value = true
  try {
    await courseApi.uploadDocument(auth.currentCourseId, file.value)
    file.value = null
    ElMessage.success('资料已上传，系统正在后台解析入库')
    await refreshAll()
    updatePolling()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    uploading.value = false
  }
}

async function reingest(doc) {
  try {
    await courseApi.reingestDocument(auth.currentCourseId, doc.source_id)
    ElMessage.success('已重新创建入库任务')
    await refreshAll()
    updatePolling()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function remove(doc) {
  await ElMessageBox.confirm('确认删除该资料？', '删除资料')
  try {
    await courseApi.deleteDocument(auth.currentCourseId, doc.source_id)
    ElMessage.success('资料已删除')
    await refreshAll()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

onMounted(refreshAll)
onUnmounted(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>

<style scoped>
.panel-card { margin-bottom: 20px; }
.card-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; font-weight: 900; color: #0f172a; }
.card-header p { margin: 6px 0 0; color: #64748b; font-size: 13px; font-weight: 500; }
.upload-text { color:#475569; font-weight: 800; }
.upload-hint { margin-top: 8px; color:#94a3b8; font-size: 13px; }
.task-card { border-radius: 24px; }
.task-empty { padding: 28px 0; }
.task-list { display: grid; gap: 12px; }
.task-item { display: grid; grid-template-columns: 1fr 150px; gap: 16px; align-items: center; padding: 14px; border-radius: 18px; background: rgba(15,23,42,.05); border: 1px solid rgba(148,163,184,.20); }
.task-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.task-title span { color: #0f172a; font-weight: 900; }
.task-main p { margin: 0 0 10px; color: #64748b; line-height: 1.6; }
.task-time { display: grid; justify-items: end; gap: 6px; color: #94a3b8; font-size: 12px; }
.task-time b { color: #475569; font-size: 13px; }
.toolbar { color:#fff; }
.toolbar h2 { margin:0; }
.doc-card { border-radius: 22px; }
.doc-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.doc-card h3 { margin:0 0 10px; color:#0f172a; }
.doc-card p { color:#64748b; }
.actions { display:flex; gap:10px; margin-top:14px; }
.table-card { margin-top:18px; }
@media (max-width: 760px) { .task-item { grid-template-columns: 1fr; } .task-time { justify-items: start; } }
</style>
