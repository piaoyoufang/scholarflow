<template>
  <div>
    <h1 class="page-title">AI 问答</h1><p class="page-desc">基于当前课程资料进行带引用问答，支持多轮追问与回答反馈。</p>
    <div v-if="!auth.hasCourse" class="empty-state">请先在“我的课程”里创建或选择一门课程。</div>
    <template v-else>
      <div class="chat-layout">
      <el-card class="session-card">
        <div class="session-header">
          <span>历史会话</span>
          <el-button size="small" type="primary" @click="newConversation">新建</el-button>
        </div>
        <el-scrollbar class="session-list">
          <div v-if="!sessions.length" class="session-empty">暂无历史会话</div>
          <button
            v-for="thread in sessions"
            :key="thread.thread_id"
            class="session-item"
            :class="{ active: thread.thread_id === auth.threadId }"
            @click="openThread(thread.thread_id)"
          >
            <span>{{ thread.title || '新会话' }}</span>
            <el-button text type="danger" size="small" @click.stop="removeThread(thread.thread_id)">删除</el-button>
          </button>
        </el-scrollbar>
      </el-card>

      <div class="chat-main">
      <el-card class="chat-card">
        <div v-if="!displayMessages.length" class="empty-state">输入课程相关问题，系统会检索知识库并生成带引用回答。</div>
        <div v-for="(m,i) in displayMessages" :key="i" class="msg" :class="m.role">
          <div class="role">{{ m.role === 'user' ? '我的问题' : 'AI 助手' }}</div>
          <MarkdownRenderer v-if="m.role === 'assistant'" :source="m.content" />
          <div v-else class="user-question">{{ m.content }}</div>
        </div>
      </el-card>
      <el-card v-if="auth.lastQuestion && auth.lastAnswer && !feedbackSubmitted" class="panel-card feedback">
        <div class="toolbar"><h2>对上一条回答反馈</h2></div>
        <el-button type="primary" @click="feedbackUp">有帮助</el-button>
        <el-form class="down-form" :model="down" label-position="top">
          <el-form-item label="没帮助的原因"><el-select v-model="down.reason"><el-option v-for="r in reasons" :key="r" :label="r" :value="r" /></el-select></el-form-item>
          <el-form-item label="补充说明"><el-input v-model="down.comment" type="textarea" /></el-form-item>
          <el-button @click="feedbackDown">没帮助</el-button>
        </el-form>
      </el-card>
      <el-card class="ask-bar">
        <el-input v-model="question" placeholder="输入课程相关问题" @keyup.enter="ask" />
        <el-button type="primary" :loading="asking" @click="ask">发送</el-button>
      </el-card>
      </div>
      </div>
    </template>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { courseApi, threadApi } from '../api'
import { errorMessage } from '../api/request'
import { useAuthStore } from '../stores/auth'
const auth=useAuthStore(); const question=ref(''); const asking=ref(false); const reasons=['答案不准确','没有引用','引用不相关','回答太少','没看懂','其他']; const down=reactive({reason:'答案不准确',comment:''})
const sessions = ref([])
const feedbackSubmitted = ref(false)
function normalizeRole(role) {
  if (['user', 'human'].includes(role)) return 'user'
  return 'assistant'
}
function normalizeContent(message) {
  if (typeof message === 'string') return message
  const content = message?.content || message?.text || message?.answer || message?.data?.content || ''
  return Array.isArray(content) ? content.map((item) => item?.text || item?.content || String(item)).join('') : content
}
const displayMessages = computed(() => {
  const normalized = (auth.messages || [])
    .map((message) => ({
      role: normalizeRole(message.role || message.type),
      content: normalizeContent(message)
    }))
    .filter((message) => message.content)

  const hasLastQuestion = normalized.some(
    (message) => message.role === 'user' && message.content === auth.lastQuestion
  )
  const hasLastAnswer = normalized.some(
    (message) => message.role === 'assistant' && message.content === auth.lastAnswer
  )
  if (auth.lastQuestion && auth.lastAnswer && hasLastAnswer && !hasLastQuestion) {
    const answerIndex = normalized.findIndex(
      (message) => message.role === 'assistant' && message.content === auth.lastAnswer
    )
    normalized.splice(Math.max(answerIndex, 0), 0, {
      role: 'user',
      content: auth.lastQuestion
    })
  }
  return normalized
})
function withCitations(result){ let txt=String(result.answer ?? JSON.stringify(result)); const cs=result.citations||[]; if(cs.length){ txt+='\n\n#### 引用来源\n'+cs.map(c=>`- ${c.source_name||c.source||'未知来源'} ${c.locator||''}: ${c.quote||c.content||''}`).join('\n') } return txt }
async function ask(){ if(!question.value.trim()) return; const q=question.value.trim(); feedbackSubmitted.value=true; auth.lastQuestion=q; auth.messages.push({role:'user',content:q}); auth.persist(); question.value=''; asking.value=true; try{ const {data}=await courseApi.ask(auth.currentCourseId,{question:q,thread_id:auth.threadId}); const answer=withCitations(data); auth.lastAnswer=answer; auth.messages.push({role:'assistant',content:answer}); feedbackSubmitted.value=false; auth.persist(); await loadThreads() }catch(e){ auth.messages.push({role:'assistant',content:`请求失败：${errorMessage(e)}`}); auth.persist() }finally{ asking.value=false } }
async function loadThreads() {
  try {
    const { data } = await threadApi.list()
    sessions.value = data.threads || []
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}
async function openThread(threadId) {
  if (threadId === auth.threadId) return
  try {
    const { data } = await threadApi.detail(threadId)
    auth.setThread(data.thread_id, data.history || [])
    const messages = displayMessages.value
    const lastUser = [...messages].reverse().find((message) => message.role === 'user')
    const lastAssistant = [...messages].reverse().find((message) => message.role === 'assistant')
    auth.lastQuestion = lastUser?.content || ''
    auth.lastAnswer = lastAssistant?.content || ''
    feedbackSubmitted.value = true
    auth.persist()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}
function newConversation() {
  auth.newThread()
  feedbackSubmitted.value = true
  ElMessage.success('已创建新会话')
}
async function removeThread(threadId) {
  try {
    await ElMessageBox.confirm('删除后无法恢复该会话记录，确定继续吗？', '删除会话', { type: 'warning' })
    await threadApi.remove(threadId)
    if (threadId === auth.threadId) auth.newThread()
    await loadThreads()
    ElMessage.success('会话已删除')
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(errorMessage(e))
  }
}
watch(() => auth.currentCourseId, loadThreads)
onMounted(loadThreads)
async function feedbackUp(){ await courseApi.feedback(auth.currentCourseId,{thread_id:auth.threadId,question:auth.lastQuestion,answer:auth.lastAnswer,rating:'up',reason:'',comment:''}); feedbackSubmitted.value=true; ElMessage.success('感谢反馈') }
async function feedbackDown(){ await courseApi.feedback(auth.currentCourseId,{thread_id:auth.threadId,question:auth.lastQuestion,answer:auth.lastAnswer,rating:'down',reason:down.reason,comment:down.comment}); feedbackSubmitted.value=true; ElMessage.success('反馈已记录') }
</script>
<style scoped>
.chat-layout { max-width: 1180px; margin: 0 auto; display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 16px; }
.session-card { height: 620px; border-radius: 22px; }
.session-header { display: flex; align-items: center; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid rgba(148,163,184,.16); color: #fff; font-weight: 900; }
.session-list { height: 545px; margin-top: 10px; }
.session-empty { padding: 28px 8px; color: #94a3b8; text-align: center; font-size: 13px; }
.session-item { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 10px; margin-bottom: 6px; border: 1px solid transparent; border-radius: 12px; background: transparent; color: #cbd5e1; cursor: pointer; text-align: left; }
.session-item > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 700; }
.session-item:hover, .session-item.active { background: rgba(37,99,235,.16); border-color: rgba(96,165,250,.30); color: #fff; }
.chat-main { min-width: 0; }
.chat-card {
  min-height: 430px;
  margin: 0 0 16px;
  border-radius: 22px;
}
.msg {
  width: fit-content;
  max-width: min(760px, 76%);
  margin: 16px 0;
  padding: 14px 16px;
  border-radius: 18px;
  line-height: 1.8;
}
.msg.user {
  margin-left: auto;
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  color: #fff;
  border-top-right-radius: 8px;
  box-shadow: 0 12px 26px rgba(37, 99, 235, .22);
}
.user-question {
  white-space: pre-wrap;
  word-break: break-word;
  font-weight: 700;
}
.msg.assistant {
  background: rgba(15, 23, 42, .70);
  color: #e2e8f0;
  border: 1px solid rgba(148, 163, 184, .26);
  border-top-left-radius: 8px;
}
.role {
  font-size: 12px;
  font-weight: 900;
  margin-bottom: 8px;
  opacity: .76;
}
.ask-bar {
  margin: 0;
  display: grid;
  grid-template-columns: 1fr 110px;
  gap: 12px;
}
.feedback {
  max-width: 1180px;
  margin: 0 auto 16px;
}
.down-form { margin-top:14px; }
@media (max-width: 900px) {
  .chat-layout { grid-template-columns: 1fr; }
  .session-card { height: auto; }
  .session-list { height: 180px; }
  .msg { max-width: 92%; }
  .ask-bar { grid-template-columns: 1fr; }
}
</style>
