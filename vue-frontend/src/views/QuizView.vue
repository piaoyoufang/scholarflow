<template>
  <div>
    <h1 class="page-title">自动出题</h1>
    <p class="page-desc">围绕指定主题自动生成选择题、判断题、简答题或面试题。</p>

    <div v-if="!auth.hasCourse" class="empty-state">请先选择课程。</div>

    <el-card v-else class="panel-card quiz-form-card">
      <el-form :model="form" label-position="top">
        <el-form-item label="出题主题">
          <el-input v-model="form.topic" placeholder="例如：RAG 检索增强生成" />
        </el-form-item>

        <!-- 改动点：使用 Element Plus 响应式栅格，PC 三列，手机自动变一列 -->
        <el-row :gutter="16" class="responsive-row">
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="题目数量">
              <el-input-number v-model="form.question_count" :min="1" :max="20" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="题型">
              <el-select v-model="form.question_type" placeholder="请选择题型">
                <el-option v-for="item in typeOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="难度">
              <el-select v-model="form.difficulty" placeholder="请选择难度">
                <el-option v-for="item in difficultyOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-button type="primary" :loading="loading" @click="generate">生成题目</el-button>
      </el-form>
    </el-card>

    <el-card v-if="auth.hasCourse" class="panel-card history-card">
      <template #header>
        <div class="history-header">
          <span>历史题单</span>
          <el-button text type="primary" @click="loadHistory">刷新</el-button>
        </div>
      </template>
      <el-empty v-if="!history.length" description="暂未生成题单" :image-size="72" />
      <div v-else class="history-list">
        <div v-for="record in history" :key="record.record_id" class="history-item" :class="{ active: record.record_id === activeRecordId }">
          <button class="history-main" @click="openHistory(record.record_id)">
            <b>{{ record.topic }}</b>
            <span>{{ typeText(record.question_type) }} · {{ difficultyText(record.difficulty) }} · {{ record.question_count }} 题</span>
            <small>{{ formatTime(record.created_at) }}</small>
          </button>
          <el-button text type="danger" @click="removeHistory(record.record_id)">删除</el-button>
        </div>
      </div>
    </el-card>

    <section v-if="items.length" class="result-section">
      <div class="result-header">
        <div>
          <h2>生成的题目</h2>
          <p>共 {{ items.length }} 道题，可用于课堂练习、课后复习或面试准备。</p>
        </div>
        <el-tag effect="plain" round>{{ questionTypeLabel }} · {{ difficultyLabel }}</el-tag>
      </div>

      <div class="question-list">
        <el-card v-for="(it, i) in items" :key="i" class="question-card">
          <div class="question-top">
            <span class="question-index">第 {{ i + 1 }} 题</span>
            <el-tag size="small" effect="plain">{{ questionTypeLabel }}</el-tag>
          </div>

          <h3>{{ it.question || '未命名题目' }}</h3>

          <ul v-if="(it.options || []).length" class="option-list">
            <li v-for="(op, j) in it.options || []" :key="j">
              <span>{{ optionLetter(j) }}</span>
              <p>{{ op }}</p>
            </li>
          </ul>

          <div class="answer-grid">
            <div class="answer-box">
              <b>参考答案</b>
              <p>{{ it.answer || '暂无' }}</p>
            </div>
            <div v-if="it.explanation" class="answer-box explanation">
              <b>解析</b>
              <p>{{ it.explanation }}</p>
            </div>
          </div>
        </el-card>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { courseApi } from '../api'
import { errorMessage } from '../api/request'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const items = ref([])
const history = ref([])
const activeRecordId = ref('')
const form = reactive({ topic: '', question_count: 5, question_type: 'single_choice', difficulty: 'easy' })
const typeOptions = [
  { label: '单选题', value: 'single_choice' },
  { label: '判断题', value: 'true_false' },
  { label: '简答题', value: 'short_answer' },
  { label: '面试题', value: 'interview' }
]
const difficultyOptions = [
  { label: '简单', value: 'easy' },
  { label: '中等', value: 'medium' },
  { label: '困难', value: 'hard' }
]
const questionTypeLabel = computed(() => typeOptions.find((item) => item.value === form.question_type)?.label || '题目')
const difficultyLabel = computed(() => difficultyOptions.find((item) => item.value === form.difficulty)?.label || '难度')

function optionLetter(index) {
  return String.fromCharCode(65 + index)
}

async function generate() {
  if (!form.topic.trim()) return ElMessage.error('出题主题不能为空')
  loading.value = true
  try {
    const { data } = await courseApi.quiz(auth.currentCourseId, { ...form, topic: form.topic.trim() })
    items.value = data.items || []
    activeRecordId.value = data.record_id || ''
    await loadHistory()
    ElMessage.success('题目生成成功')
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    loading.value = false
  }
}

function typeText(value) {
  return typeOptions.find((item) => item.value === value)?.label || value
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
    const { data } = await courseApi.quizHistory(auth.currentCourseId)
    history.value = data.items || []
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function openHistory(recordId) {
  try {
    const { data } = await courseApi.quizHistoryDetail(auth.currentCourseId, recordId)
    const record = data.record
    form.topic = record.topic
    form.question_count = record.question_count
    form.question_type = record.question_type
    form.difficulty = record.difficulty
    items.value = record.result?.items || []
    activeRecordId.value = record.record_id
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function removeHistory(recordId) {
  try {
    await ElMessageBox.confirm('删除后无法恢复该题单，确定继续吗？', '删除题单', { type: 'warning' })
    await courseApi.removeQuizHistory(auth.currentCourseId, recordId)
    if (activeRecordId.value === recordId) {
      activeRecordId.value = ''
      items.value = []
    }
    await loadHistory()
    ElMessage.success('题单已删除')
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(errorMessage(e))
  }
}

watch(() => auth.currentCourseId, () => {
  items.value = []
  activeRecordId.value = ''
  loadHistory()
})
onMounted(loadHistory)
</script>

<style scoped>
.quiz-form-card { margin-bottom: 22px; }
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
.question-list { display: grid; gap: 16px; }
.question-card { border-radius: 22px; border: 1px solid rgba(96,165,250,.28); background: linear-gradient(135deg, rgba(15,23,42,.92), rgba(15,23,42,.78)); box-shadow: 0 16px 36px rgba(15,23,42,.28); }
.question-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.question-index { display: inline-flex; height: 28px; align-items: center; padding: 0 12px; border-radius: 999px; background: rgba(37,99,235,.16); color: #93c5fd; font-size: 12px; font-weight: 900; border: 1px solid rgba(96,165,250,.28); }
.question-card h3 { margin: 14px 0 14px; color: #f8fafc; font-size: 18px; line-height: 1.7; font-weight: 900; }
.option-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
.option-list li { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; border-radius: 14px; background: rgba(255,255,255,.04); border: 1px solid rgba(148,163,184,.14); }
.option-list span { flex: 0 0 24px; width: 24px; height: 24px; display: grid; place-items: center; border-radius: 999px; background: #2563eb; color: #fff; font-size: 12px; font-weight: 900; }
.option-list p { margin: 0; color: #e2e8f0; line-height: 1.7; }
.answer-grid { display: grid; gap: 12px; margin-top: 14px; }
.answer-box { padding: 12px 14px; border-radius: 16px; background: rgba(14,165,233,.10); border: 1px solid rgba(14,165,233,.24); }
.answer-box b { color: #93c5fd; }
.answer-box p { margin: 6px 0 0; color: #e2e8f0; line-height: 1.7; }
.answer-box.explanation { background: rgba(34,197,94,.08); border-color: rgba(34,197,94,.20); }
</style>
