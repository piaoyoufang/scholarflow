<template>
  <div>
    <h1 class="page-title">学习计划</h1>
    <p class="page-desc">输入学习目标，由 Agent 按天拆解任务、产出和难度节奏。</p>

    <div v-if="!auth.hasCourse" class="empty-state">请先选择课程。</div>

    <el-card v-else class="panel-card plan-form-card">
      <el-form :model="form" label-position="top">
        <el-form-item label="学习目标">
          <el-input v-model="form.goal" type="textarea" :rows="3" placeholder="例如：7天内掌握本课程的 RAG 项目开发流程" />
        </el-form-item>

        <div class="grid grid-3">
          <el-form-item label="计划天数">
            <el-input-number v-model="form.days" :min="1" :max="30" />
          </el-form-item>
          <el-form-item label="每天学习分钟数">
            <el-input-number v-model="form.daily_minutes" :min="10" :max="600" />
          </el-form-item>
          <el-form-item label="难度">
            <el-select v-model="form.difficulty" placeholder="请选择难度">
              <el-option v-for="item in difficultyOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
        </div>

        <el-button type="primary" :loading="loading" @click="generate">生成学习计划</el-button>
      </el-form>
    </el-card>

    <el-card v-if="auth.hasCourse" class="panel-card history-card">
      <template #header>
        <div class="history-header">
          <span>历史学习计划</span>
          <el-button text type="primary" @click="loadHistory">刷新</el-button>
        </div>
      </template>
      <el-empty v-if="!history.length" description="暂未生成学习计划" :image-size="72" />
      <div v-else class="history-list">
        <div v-for="record in history" :key="record.record_id" class="history-item" :class="{ active: record.record_id === activeRecordId }">
          <button class="history-main" @click="openHistory(record.record_id)">
            <b>{{ record.goal }}</b>
            <span>{{ record.days }} 天 · {{ difficultyText(record.difficulty) }} · {{ record.daily_minutes }} 分钟/天</span>
            <small>{{ formatTime(record.created_at) }}</small>
          </button>
          <el-button text type="danger" @click="removeHistory(record.record_id)">删除</el-button>
        </div>
      </div>
    </el-card>

    <section v-if="days.length" class="result-section">
      <div class="result-header">
        <div>
          <h2>生成的学习计划</h2>
          <p>共 {{ days.length }} 天，按主题、任务和预期产出拆解。</p>
        </div>
        <el-tag effect="plain" round>AI 规划结果</el-tag>
      </div>

      <div class="plan-list">
        <el-card v-for="d in days" :key="d.day" class="plan-day-card">
          <div class="day-index">第 {{ d.day }} 天</div>
          <h3>{{ d.topic || '未命名主题' }}</h3>
          <ul v-if="(d.tasks || []).length" class="task-list">
            <li v-for="(t, i) in d.tasks || []" :key="i">
              <span>{{ i + 1 }}</span>
              <p>{{ t }}</p>
            </li>
          </ul>
          <div v-if="d.expected_output" class="output-box">
            <b>预期产出</b>
            <p>{{ d.expected_output }}</p>
          </div>
        </el-card>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { courseApi } from '../api'
import { errorMessage } from '../api/request'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const days = ref([])
const history = ref([])
const activeRecordId = ref('')
const form = reactive({ goal: '', days: 7, daily_minutes: 60, difficulty: 'beginner' })
const difficultyOptions = [
  { label: '入门', value: 'beginner' },
  { label: '进阶', value: 'intermediate' },
  { label: '高级', value: 'advanced' }
]

async function generate() {
  if (!form.goal.trim()) return ElMessage.error('学习目标不能为空')
  loading.value = true
  try {
    const { data } = await courseApi.learningPlan(auth.currentCourseId, { ...form, goal: form.goal.trim() })
    days.value = data.days || []
    activeRecordId.value = data.record_id || ''
    await loadHistory()
    ElMessage.success('学习计划生成成功')
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    loading.value = false
  }
}

function difficultyText(value) {
  return difficultyOptions.find((item) => item.value === value)?.label || value
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : ''
}

async function loadHistory() {
  if (!auth.currentCourseId) return
  try {
    const { data } = await courseApi.learningPlanHistory(auth.currentCourseId)
    history.value = data.items || []
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function openHistory(recordId) {
  try {
    const { data } = await courseApi.learningPlanHistoryDetail(auth.currentCourseId, recordId)
    const record = data.record
    form.goal = record.goal
    form.days = record.days
    form.difficulty = record.difficulty
    form.daily_minutes = record.daily_minutes
    days.value = record.result?.days || []
    activeRecordId.value = record.record_id
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function removeHistory(recordId) {
  try {
    await ElMessageBox.confirm('删除后无法恢复该学习计划，确定继续吗？', '删除学习计划', { type: 'warning' })
    await courseApi.removeLearningPlanHistory(auth.currentCourseId, recordId)
    if (activeRecordId.value === recordId) {
      activeRecordId.value = ''
      days.value = []
    }
    await loadHistory()
    ElMessage.success('学习计划已删除')
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(errorMessage(e))
  }
}

watch(() => auth.currentCourseId, () => {
  days.value = []
  activeRecordId.value = ''
  loadHistory()
})
onMounted(loadHistory)
</script>

<style scoped>
.plan-form-card { margin-bottom: 22px; }
.history-card { margin-bottom: 22px; }
.history-header { display: flex; align-items: center; justify-content: space-between; font-weight: 900; color: #0f172a; }
.history-list { display: grid; gap: 10px; }
.history-item { display: flex; gap: 12px; align-items: center; padding: 10px 12px; border: 1px solid rgba(148,163,184,.22); border-radius: 14px; }
.history-item.active { border-color: #3b82f6; background: rgba(37,99,235,.08); }
.history-main { flex: 1; display: grid; gap: 4px; border: 0; padding: 0; background: transparent; text-align: left; cursor: pointer; }
.history-main b { color: #0f172a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-main span, .history-main small { color: #64748b; font-size: 12px; }
.result-section { margin-top: 20px; }
.result-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-end; margin-bottom: 16px; color: #fff; }
.result-header h2 { margin: 0 0 6px; font-size: 22px; font-weight: 900; }
.result-header p { margin: 0; color: #cbd5e1; }
.plan-list { display: grid; gap: 16px; }
.plan-day-card { border-radius: 22px; border: 1px solid rgba(96,165,250,.28); background: linear-gradient(135deg, rgba(15,23,42,.92), rgba(15,23,42,.78)); box-shadow: 0 16px 36px rgba(15,23,42,.28); }
.day-index { display: inline-flex; height: 28px; align-items: center; padding: 0 12px; border-radius: 999px; background: rgba(37,99,235,.16); color: #93c5fd; font-size: 12px; font-weight: 900; border: 1px solid rgba(96,165,250,.28); }
.plan-day-card h3 { margin: 12px 0 14px; color: #f8fafc; font-size: 18px; font-weight: 900; }
.task-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
.task-list li { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; border-radius: 14px; background: rgba(255,255,255,.04); border: 1px solid rgba(148,163,184,.14); }
.task-list span { flex: 0 0 24px; width: 24px; height: 24px; display: grid; place-items: center; border-radius: 999px; background: #2563eb; color: #fff; font-size: 12px; font-weight: 900; }
.task-list p { margin: 0; color: #e2e8f0; line-height: 1.7; }
.output-box { margin-top: 14px; padding: 12px 14px; border-radius: 16px; background: rgba(14,165,233,.10); border: 1px solid rgba(14,165,233,.24); }
.output-box b { color: #93c5fd; }
.output-box p { margin: 6px 0 0; color: #e2e8f0; line-height: 1.7; }
</style>
