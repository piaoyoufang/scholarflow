<template>
  <div class="analytics-page">
    <h1 class="page-title">问答分析</h1>
    <p class="page-desc">统计课程问答、引用覆盖、学生负反馈和待处理问题，帮助教师优化课程资料。</p>

    <div v-if="!auth.hasCourse" class="empty-state">请先选择课程。</div>

    <template v-else>
      <el-card class="panel-card action-card">
        <div>
          <h2>分析数据概览</h2>
          <p>点击刷新后会读取当前课程的问答记录、引用情况和学生反馈。</p>
        </div>
        <el-button type="primary" :loading="loading" @click="loadAll">刷新分析数据</el-button>
      </el-card>

      <div class="summary-grid">
        <el-card v-for="item in summaryCards" :key="item.label" class="summary-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small>{{ item.desc }}</small>
        </el-card>
      </div>

      <el-card class="panel-card table-card">
        <template #header>
          <div class="card-header">
            <span>高频问题</span>
            <el-tag effect="plain">{{ topQuestions.length }} 条</el-tag>
          </div>
        </template>
        <el-empty v-if="!topQuestions.length" description="暂无高频问题。需要学生围绕相同问题多次提问后才会形成统计。" />
        <el-table v-else :data="topQuestions" stripe>
          <el-table-column type="index" label="#" width="70" />
          <el-table-column prop="question" label="问题内容" min-width="360" show-overflow-tooltip />
          <el-table-column prop="count" label="出现次数" width="120" />
        </el-table>
      </el-card>

      <el-card class="panel-card table-card">
        <template #header>
          <div class="card-header">
            <span>无引用问题</span>
            <el-tag effect="plain">{{ noCitation.length }} 条</el-tag>
          </div>
        </template>
        <el-empty v-if="!noCitation.length" description="暂无无引用问题。说明当前回答基本都有资料引用，或暂未产生问答记录。" />
        <el-table v-else :data="noCitation" stripe>
          <el-table-column prop="question" label="问题" min-width="260" show-overflow-tooltip />
          <el-table-column prop="answer" label="回答摘要" min-width="320" show-overflow-tooltip />
          <el-table-column prop="created_at" label="时间" width="180" :formatter="timeFormatter" />
        </el-table>
      </el-card>

      <el-card class="panel-card table-card">
        <template #header>
          <div class="card-header">
            <span>负反馈问题</span>
            <el-tag type="danger" effect="plain">{{ downFeedback.length }} 条</el-tag>
          </div>
        </template>
        <el-empty v-if="!downFeedback.length" description="暂无学生负反馈。学生点击“没帮助”后，会在这里出现记录。" />
        <el-table v-else :data="downFeedback" stripe>
          <el-table-column prop="question" label="问题" min-width="260" show-overflow-tooltip />
          <el-table-column prop="reason" label="原因" width="160" />
          <el-table-column prop="comment" label="补充说明" min-width="220" show-overflow-tooltip />
          <el-table-column prop="created_at" label="反馈时间" width="180" :formatter="timeFormatter" />
        </el-table>
      </el-card>

      <el-card class="panel-card table-card">
        <template #header>
          <div class="card-header">
            <span>低质量问题处理</span>
            <el-tag effect="plain">{{ lowQuality.length }} 条</el-tag>
          </div>
        </template>
        <el-empty v-if="!lowQuality.length" description="暂无自动判定的低质量问题。你也可以优先查看上方“负反馈问题”。" />
        <el-form v-else :model="processForm" label-position="top" class="process-form">
          <el-form-item label="选择问答事件">
            <el-select v-model="processForm.event_id" filterable placeholder="请选择低质量问答事件">
              <el-option
                v-for="it in lowQuality"
                :key="it.event_id"
                :label="String(it.question || '').slice(0, 80)"
                :value="it.event_id"
              />
            </el-select>
          </el-form-item>
          <el-row :gutter="16">
            <el-col :xs="24" :md="8">
              <el-form-item label="处理状态">
                <el-select v-model="processForm.status">
                  <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :md="16">
              <el-form-item label="处理备注">
                <el-input v-model="processForm.note" type="textarea" placeholder="例如：已补充课程资料，或该问题无需处理" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-button type="primary" :loading="updating" @click="updateStatus">更新处理状态</el-button>
        </el-form>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { courseApi } from '../api'
import { errorMessage } from '../api/request'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const updating = ref(false)
const dashboard = ref({})
const topQuestions = ref([])
const noCitation = ref([])
const lowQuality = ref([])
const downFeedback = ref([])
const processForm = reactive({ event_id: '', status: 'pending', note: '' })
const statusOptions = [
  { label: '待处理', value: 'pending' },
  { label: '处理中', value: 'processing' },
  { label: '已解决', value: 'resolved' },
  { label: '已忽略', value: 'ignored' }
]

const summaryCards = computed(() => [
  { label: '问答总数', value: dashboard.value.qa_count ?? 0, desc: '当前课程累计问答次数' },
  { label: '引用覆盖率', value: `${Math.round((dashboard.value.citation_rate || 0) * 100)}%`, desc: '回答命中课程资料的比例' },
  { label: '无引用问题', value: dashboard.value.no_citation_count ?? 0, desc: '需要补充资料或优化检索' },
  { label: '负反馈', value: dashboard.value.feedback_down_count ?? downFeedback.value.length, desc: '学生点击没帮助的次数' }
])

function timeFormatter(_row, _column, value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'
}

async function loadAll() {
  loading.value = true
  try {
    const [summaryRes, topRes, noCitationRes, lowQualityRes, downFeedbackRes] = await Promise.all([
      courseApi.dashboard(auth.currentCourseId),
      courseApi.topQuestions(auth.currentCourseId),
      courseApi.noCitation(auth.currentCourseId),
      courseApi.lowQuality(auth.currentCourseId),
      courseApi.downFeedback(auth.currentCourseId)
    ])
    dashboard.value = summaryRes.data || {}
    topQuestions.value = topRes.data.items || []
    noCitation.value = noCitationRes.data.items || []
    lowQuality.value = lowQualityRes.data.items || []
    downFeedback.value = downFeedbackRes.data.items || []
    ElMessage.success('分析数据已刷新')
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    loading.value = false
  }
}

async function updateStatus() {
  if (!processForm.event_id) return ElMessage.error('请选择要处理的问答事件')
  updating.value = true
  try {
    await courseApi.updateQaEventStatus(auth.currentCourseId, processForm.event_id, {
      status: processForm.status,
      note: processForm.note
    })
    ElMessage.success('处理状态已更新')
    await loadAll()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    updating.value = false
  }
}

watch(() => auth.currentCourseId, () => {
  dashboard.value = {}
  topQuestions.value = []
  noCitation.value = []
  lowQuality.value = []
  downFeedback.value = []
  if (auth.currentCourseId) loadAll()
})

onMounted(() => {
  if (auth.currentCourseId) loadAll()
})
</script>

<style scoped>
.analytics-page { max-width: 1180px; margin: 0 auto; }
.panel-card { margin-bottom: 18px; }
.action-card { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.action-card h2 { margin: 0 0 6px; color: #0f172a; font-size: 18px; font-weight: 900; }
.action-card p { margin: 0; color: #64748b; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
.summary-card span { color: #64748b; font-size: 13px; font-weight: 800; }
.summary-card strong { display: block; margin-top: 8px; color: #0f172a; font-size: 30px; font-weight: 900; }
.summary-card small { color: #94a3b8; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-weight: 900; color: #0f172a; }
.process-form { margin-top: 8px; }
@media (max-width: 900px) {
  .action-card { flex-direction: column; align-items: stretch; }
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  .summary-grid { grid-template-columns: 1fr; }
}
</style>
