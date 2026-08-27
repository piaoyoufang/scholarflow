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
          <template v-if="m.role === 'assistant'">
            <div class="assistant-head">
              <span class="assistant-avatar">AI</span>
              <span class="assistant-name">AI 助手</span>
              <span class="msg-time">{{ m.time }}</span>
            </div>
            <!-- 执行过程条：独立于答案正文，进行中显示当前步骤，完成后折叠为一行摘要 -->
            <div v-if="m.steps && m.steps.length" class="process" @click="m.raw.showSteps = !m.raw.showSteps">
              <span v-if="m.pending" class="process-spinner"></span>
              <span v-else class="process-check">✓</span>
              <span class="process-title">{{ m.pending ? m.steps[m.steps.length-1] + '…' : `已完成 ${m.steps.length} 个步骤` }}</span>
              <span class="process-toggle">{{ m.raw.showSteps ? '收起' : '展开' }}</span>
            </div>
            <div v-if="m.steps && (m.pending || m.raw.showSteps)" class="process-steps">
              <div v-for="(s,si) in m.steps" :key="si" class="process-step"><span class="process-check">✓</span>{{ s }}</div>
            </div>
            <MarkdownRenderer v-if="m.content" :source="m.content" />
          </template>
          <div v-else class="user-side">
            <div class="user-head">
              <span class="msg-time">{{ m.time }}</span>
              <span class="user-avatar">我</span>
            </div>
            <div class="user-question">{{ m.content }}</div>
          </div>
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
        <el-button v-if="!asking" type="primary" @click="ask">发送</el-button>
        <el-button v-else type="danger" @click="stopAsk">停止生成</el-button>
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
import { courseApi, threadApi, askCourseStream } from '../api'
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
      content: normalizeContent(message),
      // 流式过程字段：steps=执行步骤列表，pending=是否进行中，raw=原始对象引用（折叠状态写回它才能触发响应式）
      steps: message.steps,
      pending: message.pending,
      time: message.time,
      raw: message
    }))
    // pending 中的占位消息 content 还是空的，不能过滤掉，否则看不到执行过程条
    .filter((message) => message.content || message.pending)

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
// 流式问答：进度步骤放在独立的「过程条」里（不进答案正文）；
// 答案到达后用打字机效果逐段揭示——结构化输出只能整段返回，前端补一层逐字观感
const abortCtrl = ref(null)
// 消息时间戳：后端历史只存 role/content，时间由前端在收发时打上
function nowTime(){ return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }
function typewrite(target, fullText){
  return new Promise((resolve)=>{
    let i=0
    const step=Math.max(2, Math.ceil(fullText.length/120))  // 约 120 帧出完，长答案也不会拖太久
    const timer=setInterval(()=>{
      i=Math.min(fullText.length, i+step)
      target.content=fullText.slice(0,i)
      if(i>=fullText.length){ clearInterval(timer); resolve() }
    },16)
  })
}
async function ask(){
  if(!question.value.trim() || asking.value) return
  const q=question.value.trim(); feedbackSubmitted.value=true; auth.lastQuestion=q; auth.messages.push({role:'user',content:q,time:nowTime()}); question.value=''; asking.value=true
  auth.messages.push({role:'assistant', content:'', steps:['正在理解问题'], pending:true, showSteps:true})
  const pending=auth.messages[auth.messages.length-1]  // 从响应式数组里取回代理对象，改它才会触发界面更新
  auth.persist()
  abortCtrl.value=new AbortController()
  let answerPayload=null, streamError=''
  try{
    await askCourseStream(auth.currentCourseId,{question:q,thread_id:auth.threadId},{
      signal:abortCtrl.value.signal,
      onStatus:(s)=>{ if(pending.steps[pending.steps.length-1]!==s.msg) pending.steps.push(s.msg) },
      onAnswer:(data)=>{ answerPayload=withCitations(data) },
      onError:(msg)=>{ streamError=msg }
    })
    pending.pending=false
    if(answerPayload){
      await typewrite(pending, answerPayload)   // 打字机播完再 persist，否则中途落盘的是半截答案
      auth.lastAnswer=answerPayload; feedbackSubmitted.value=false
    } else if(streamError){
      pending.content=`请求失败：${streamError}`
    }
    // 先 persist 再 loadThreads：axios 请求拦截器每次都会 restoreFromStorage() 重建 messages 数组，
    // 不落盘的话本地旧快照会把刚渲染出的答案整个覆盖掉
    auth.persist()
    await loadThreads()
  }catch(e){
    // AbortError 是用户主动点「停止生成」，不算失败
    pending.pending=false
    pending.content=e?.name==='AbortError' ? '已停止生成。' : `请求失败：${errorMessage(e)}`
  }finally{ if(!pending.time) pending.time=nowTime(); asking.value=false; abortCtrl.value=null; auth.persist() }
}
function stopAsk(){ abortCtrl.value?.abort() }
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
  background: transparent;
  padding: 0;
}
.user-side { display: flex; flex-direction: column; align-items: flex-end; }
.user-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.user-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(37,99,235,.25);
  border: 1px solid rgba(96,165,250,.4);
  color: #93c5fd;
  font-size: 12px;
  font-weight: 900;
}
.msg-time { font-size: 12px; color: #64748b; }
.user-question {
  white-space: pre-wrap;
  word-break: break-word;
  font-weight: 700;
  padding: 12px 16px;
  border-radius: 18px;
  border-top-right-radius: 8px;
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  color: #fff;
  box-shadow: 0 12px 26px rgba(37, 99, 235, .22);
}
.msg.assistant {
  width: 100%;
  max-width: 100%;
  padding: 4px 0;
  background: transparent;
  color: #e2e8f0;
}
.assistant-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.assistant-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #fff;
  font-size: 11px;
  font-weight: 900;
}
.assistant-name { font-size: 13px; font-weight: 900; color: #e2e8f0; opacity: .95; }
.process {
  display: flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  margin-bottom: 8px;
  padding: 6px 12px;
  border: 1px solid rgba(148,163,184,.20);
  border-radius: 10px;
  background: rgba(148,163,184,.07);
  color: #94a3b8;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
}
.process-title { font-weight: 700; }
.process-toggle { opacity: .6; }
.process-check { color: #34d399; font-weight: 900; }
.process-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(148,163,184,.35);
  border-top-color: #60a5fa;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.process-steps {
  margin: 0 0 10px 4px;
  padding-left: 10px;
  border-left: 2px solid rgba(148,163,184,.18);
  color: #94a3b8;
  font-size: 12px;
  line-height: 2;
}
.process-step { display: flex; align-items: center; gap: 6px; }
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
