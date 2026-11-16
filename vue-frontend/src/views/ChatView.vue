<template>
  <div class="chat-page">
    <!-- 左侧：会话列表 -->
    <aside class="thread-rail">
      <button class="new-chat" type="button" @click="newConversation">
        <span class="plus">＋</span> 新建对话
      </button>
      <div class="thread-scroll">
        <div v-for="group in groupedThreads" :key="group.label" class="thread-group">
          <p class="group-label">{{ group.label }}</p>
          <button
            v-for="thread in group.items"
            :key="thread.thread_id"
            type="button"
            class="thread-item"
            :class="{ active: thread.thread_id === auth.threadId }"
            @click="openThread(thread)"
          >
            <span class="thread-title">{{ thread.title || '新会话' }}</span>
            <span class="thread-remove" title="删除会话" @click.stop="removeThread(thread)">✕</span>
          </button>
        </div>
        <p v-if="!threads.length" class="thread-empty">还没有历史会话</p>
      </div>
    </aside>

    <!-- 右侧：对话主区 -->
    <section class="conversation">
      <header class="conv-head">
        <div>
          <h1>{{ auth.currentCourseName || 'AI 问答' }}</h1>
          <p>基于课程资料检索后作答，回答会附带引用来源。</p>
        </div>
        <span class="conv-badge">RAG · 引用可溯源</span>
      </header>

      <div ref="scrollRef" class="messages" @scroll="onScroll">
        <div v-if="!messages.length" class="hero">
          <h2>今天想学点什么？</h2>
          <p>我会先检索课程知识库，再给出带出处的回答。</p>
          <div class="suggestions">
            <button
              v-for="item in suggestions"
              :key="item"
              type="button"
              @click="ask(item)"
            >{{ item }}</button>
          </div>
        </div>

        <article
          v-for="msg in messages"
          :key="msg.id"
          class="turn"
          :class="msg.role"
        >
          <div class="avatar">{{ msg.role === 'user' ? '我' : 'AI' }}</div>
          <div class="bubble-col">
            <div class="bubble">
              <MarkdownRenderer v-if="msg.role === 'assistant'" :source="msg.content" />
              <p v-else class="user-text">{{ msg.content }}</p>
              <span v-if="msg.streaming" class="caret"></span>
            </div>

            <div v-if="msg.role === 'assistant' && msg.content" class="cite-box">
              <button
                v-if="msg.citations?.length"
                type="button"
                class="cite-head"
                @click="msg.citesOpen = !msg.citesOpen"
              >
                <span>{{ msg.citations.length }} 条引用来源</span>
                <span class="chev" :class="{ open: msg.citesOpen }">▾</span>
              </button>
              <ul v-show="msg.citesOpen" class="cite-list">
                <li v-for="(cite, index) in msg.citations" :key="index">
                  <span class="cite-idx">[{{ index + 1 }}]</span>
                  <div class="cite-body">
                    <p class="cite-src">
                      {{ citeName(cite) }}
                      <span v-if="citeLocator(cite)">· {{ citeLocator(cite) }}</span>
                    </p>
                    <p class="cite-quote">{{ citeQuote(cite) }}</p>
                  </div>
                </li>
              </ul>
            </div>

            <div v-if="msg.role === 'assistant' && !msg.streaming && msg.content" class="msg-actions">
              <button type="button" @click="copyMessage(msg)">复制</button>
              <button type="button" @click="regenerate(msg)">重新生成</button>
              <button type="button" :class="{ on: msg.feedback === 'up' }" @click="feedback(msg, 'up')">有用</button>
              <button type="button" :class="{ on: msg.feedback === 'down' }" @click="feedback(msg, 'down')">没帮助</button>
            </div>
          </div>
        </article>

        <div v-if="statusText" class="status-line">
          <span class="dot"></span>{{ statusText }}
        </div>
      </div>

      <button v-if="!atBottom" type="button" class="to-bottom" @click="scrollToBottom(true)">回到底部</button>

      <footer class="composer">
        <div class="composer-box">
          <textarea
            ref="inputRef"
            v-model="question"
            rows="1"
            placeholder="输入问题，Enter 发送，Shift + Enter 换行"
            @keydown.enter.exact.prevent="ask"
            @input="autoGrow"
          ></textarea>
          <button v-if="asking" type="button" class="send stop" @click="stop">停止</button>
          <button v-else type="button" class="send" :disabled="!question.trim()" @click="ask">发送</button>
        </div>
        <p class="composer-tip">回答由 AI 基于课程资料生成，请结合引用核对原文。</p>
      </footer>
    </section>

    <el-dialog v-model="downDialog" title="告诉我们哪里不好" width="420px" append-to-body>
      <el-form label-position="top">
        <el-form-item label="主要原因">
          <el-select v-model="downForm.reason" placeholder="请选择">
            <el-option v-for="item in downReasons" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="补充说明（选填）">
          <el-input v-model="downForm.comment" type="textarea" :rows="3" maxlength="500" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="downDialog = false">取消</el-button>
        <el-button type="primary" @click="submitDownFeedback">提交反馈</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import { askCourseStream, courseApi, threadApi } from '../api'
import { errorMessage } from '../api/request'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

const threads = ref([])
const messages = ref([])
const question = ref('')
const asking = ref(false)
const statusText = ref('')
const scrollRef = ref(null)
const inputRef = ref(null)
const atBottom = ref(true)
const abortController = ref(null)

const downDialog = ref(false)
const downTarget = ref(null)
const downForm = reactive({ reason: '', comment: '' })
const downReasons = ['回答不准确', '引用与原文不符', '内容不完整', '答非所问', '其他']

let seq = 0
const makeId = () => `${Date.now()}-${seq++}`

const suggestions = computed(() => {
  const course = auth.currentCourseName || '本课程'
  return [
    `帮我梳理《${course}》的核心知识点`,
    '用通俗的例子解释最难理解的概念',
    '生成一份 30 分钟的复习提纲',
    '这个知识点在考试中常怎么考？'
  ]
})

// 引用展示前统一清洗：UUID、长十六进制串属于内部标识，不能出现在前端
const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi
const HEX_ONLY_RE = /^(?:[0-9a-f]{12,}|[0-9a-f]+[-_][0-9a-f-_]+)$/i

function cleanCiteText(value) {
  return String(value ?? '')
    .replace(UUID_RE, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function citeName(cite) {
  const name = cleanCiteText(cite?.source_name)
  return !name || HEX_ONLY_RE.test(name) ? '课程资料' : name
}

function citeLocator(cite) {
  const locator = cleanCiteText(cite?.locator)
  return !locator || HEX_ONLY_RE.test(locator) ? '' : locator
}

function citeQuote(cite) {
  return cleanCiteText(cite?.quote)
}

const groupedThreads = computed(() => {
  const startOfToday = new Date()
  startOfToday.setHours(0, 0, 0, 0)
  const today = startOfToday.getTime()
  const groups = [
    { label: '今天', items: [] },
    { label: '昨天', items: [] },
    { label: '更早', items: [] }
  ]
  for (const thread of threads.value) {
    const raw = String(thread.updated_at || thread.created_at || '').replace(/([+-]\d{2})(\d{2})$/, '$1:$2')
    const time = new Date(raw).getTime()
    const bucket = !Number.isFinite(time) || time < today - 86400000 ? 2 : time < today ? 1 : 0
    groups[bucket].items.push(thread)
  }
  return groups.filter((group) => group.items.length)
})

function normalizeHistory(history) {
  const list = []
  for (const item of history || []) {
    const role = item.role || (item.type === 'ai' || item.type === 'assistant' ? 'assistant' : 'user')
    const content = typeof item.content === 'string' ? item.content : item.content?.text || ''
    if (!content) continue
    const message = {
      id: makeId(),
      role,
      content,
      citations: [],
      streaming: false,
      question: '',
      feedback: '',
      citesOpen: false
    }
    if (role === 'assistant' && list.length) {
      const previous = [...list].reverse().find((entry) => entry.role === 'user')
      message.question = previous?.content || ''
    }
    list.push(message)
  }
  return list
}

function syncAuthMessages() {
  const history = messages.value
    .filter((msg) => !msg.streaming && msg.content)
    .map((msg) => ({ role: msg.role, content: msg.content }))
  auth.messages = history
  const lastAnswer = [...messages.value].reverse().find((msg) => msg.role === 'assistant' && msg.content)
  const lastQuestion = [...messages.value].reverse().find((msg) => msg.role === 'user' && msg.content)
  auth.lastAnswer = lastAnswer?.content || ''
  auth.lastQuestion = lastQuestion?.content || ''
  auth.persist()
}

async function loadThreads() {
  try {
    const { data } = await threadApi.list()
    threads.value = data.threads || []
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function openThread(thread) {
  if (asking.value) return
  if (thread.thread_id === auth.threadId && messages.value.length) return
  try {
    const { data } = await threadApi.detail(thread.thread_id)
    auth.setThread(thread.thread_id, data.history || [])
    messages.value = normalizeHistory(data.history)
    statusText.value = ''
    scrollToBottom()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

function newConversation() {
  if (asking.value) return
  auth.newThread()
  messages.value = []
  statusText.value = ''
  question.value = ''
  autoGrow()
  nextTick(() => inputRef.value?.focus())
}

async function removeThread(thread) {
  try {
    await ElMessageBox.confirm('删除后该会话的历史消息将无法恢复，确定删除吗？', '删除会话', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    await threadApi.remove(thread.thread_id)
    threads.value = threads.value.filter((item) => item.thread_id !== thread.thread_id)
    if (thread.thread_id === auth.threadId) newConversation()
    ElMessage.success('会话已删除')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

function onScroll() {
  const el = scrollRef.value
  if (!el) return
  atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

function scrollToBottom(smooth = false) {
  nextTick(() => {
    const el = scrollRef.value
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  })
}

function autoGrow() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`
}

async function ask(text) {
  if (!auth.currentCourseId) {
    ElMessage.warning('请先选择课程')
    return
  }
  const content = (typeof text === 'string' ? text : question.value).trim()
  if (!content || asking.value) return

  question.value = ''
  autoGrow()

  const userMessage = {
    id: makeId(),
    role: 'user',
    content,
    citations: [],
    streaming: false,
    question: '',
    feedback: '',
    citesOpen: false
  }
  const answerMessage = {
    id: makeId(),
    role: 'assistant',
    content: '',
    citations: [],
    streaming: true,
    question: content,
    feedback: '',
    citesOpen: false
  }
  messages.value.push(userMessage, answerMessage)
  // ref 数组里的对象需要取回响应式代理再修改，直接改原始对象不会触发视图更新
  const answerRef = messages.value[messages.value.length - 1]
  asking.value = true
  statusText.value = '正在检索课程知识库…'
  atBottom.value = true
  scrollToBottom()

  const controller = new AbortController()
  abortController.value = controller

  // 模型逐 token 推送，直接改响应式内容会频繁重渲染 Markdown，这里按 60ms 节流刷新
  let pending = ''
  let lastFlush = 0
  const flush = (force = false) => {
    const now = performance.now()
    if (!force && now - lastFlush < 60) return
    lastFlush = now
    answerRef.content = pending
    if (atBottom.value) scrollToBottom()
  }

  try {
    await askCourseStream(
      auth.currentCourseId,
      { question: content, thread_id: auth.threadId },
      {
        token: auth.accessToken,
        meta: (data) => {
          if (data.stage === 'answering') statusText.value = '正在生成回答…'
        },
        delta: (data) => {
          pending += data.text || ''
          flush()
        },
        done: (data) => {
          if (data.answer) pending = data.answer
          flush(true)
          answerRef.citations = data.citations || []
        }
      },
      controller.signal
    )
    answerRef.streaming = false
    statusText.value = ''
    syncAuthMessages()
    loadThreads()
  } catch (error) {
    answerRef.streaming = false
    statusText.value = ''
    if (error?.name === 'AbortError') {
      if (!answerRef.content.trim()) {
        messages.value = messages.value.filter((msg) => msg.id !== answerRef.id)
      }
      ElMessage.info('已停止生成')
    } else {
      answerRef.content = answerRef.content || `请求失败：${errorMessage(error)}`
      ElMessage.error(errorMessage(error))
    }
    syncAuthMessages()
  } finally {
    asking.value = false
    abortController.value = null
  }
}

function stop() {
  abortController.value?.abort()
}

async function copyMessage(msg) {
  try {
    await navigator.clipboard.writeText(msg.content)
    ElMessage.success('已复制回答')
  } catch {
    ElMessage.error('复制失败，请手动选择文本复制')
  }
}

function regenerate(msg) {
  if (asking.value) return
  const index = messages.value.findIndex((item) => item.id === msg.id)
  if (index < 0) return
  const questionText = msg.question || messages.value[index - 1]?.content
  if (!questionText) return
  const userIndex = index > 0 && messages.value[index - 1].role === 'user' ? index - 1 : index
  messages.value.splice(userIndex)
  syncAuthMessages()
  ask(questionText)
}

function feedback(msg, rating) {
  if (!msg.question) return
  if (rating === 'down') {
    downTarget.value = msg
    downForm.reason = ''
    downForm.comment = ''
    downDialog.value = true
    return
  }
  submitFeedback(msg, 'up', '', '')
}

function submitDownFeedback() {
  if (!downTarget.value) return
  const { reason, comment } = downForm
  downDialog.value = false
  submitFeedback(downTarget.value, 'down', reason, comment)
}

async function submitFeedback(msg, rating, reason, comment) {
  try {
    await courseApi.feedback(auth.currentCourseId, {
      thread_id: auth.threadId,
      question: msg.question,
      answer: msg.content,
      rating,
      reason,
      comment
    })
    msg.feedback = rating
    ElMessage.success(rating === 'up' ? '感谢反馈' : '已记录，我们会持续改进')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

watch(
  () => messages.value.length,
  () => {
    if (atBottom.value) scrollToBottom()
  }
)

onMounted(() => {
  messages.value = normalizeHistory(auth.messages)
  loadThreads()
})

onBeforeUnmount(() => {
  abortController.value?.abort()
})
</script>

<style scoped>
.chat-page {
  display: grid;
  grid-template-columns: 236px minmax(0, 1fr);
  gap: 18px;
  height: calc(100dvh - 148px);
  min-height: 560px;
}

/* ---------- 左侧会话栏 ---------- */
.thread-rail {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 10px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(16px);
}

.new-chat {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 40px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.85);
  color: var(--text-2);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}
.new-chat:hover {
  background: rgba(124, 58, 237, 0.1);
  border-color: rgba(124, 58, 237, 0.32);
  color: var(--text);
}
.new-chat .plus { font-size: 15px; color: var(--primary); }

.thread-scroll { flex: 1; overflow-y: auto; padding-right: 2px; }
.thread-group + .thread-group { margin-top: 12px; }
.group-label {
  margin: 4px 6px 6px;
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--muted-2);
}

.thread-item {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 10px;
  margin-bottom: 2px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--text-2);
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
  transition: all 0.18s ease;
}
.thread-item:hover { background: rgba(124, 58, 237, 0.07); color: var(--text); }
.thread-item.active {
  background: rgba(124, 58, 237, 0.12);
  color: var(--primary);
  box-shadow: inset 0 0 0 1px rgba(124, 58, 237, 0.24);
}
.thread-title {
  flex: 1;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.thread-remove {
  opacity: 0;
  font-size: 11px;
  color: var(--muted-2);
  transition: opacity 0.18s ease;
}
.thread-item:hover .thread-remove { opacity: 1; }
.thread-remove:hover { color: #be123c; }
.thread-empty {
  margin: 18px 6px;
  font-size: 12px;
  color: var(--muted-2);
  text-align: center;
}

/* ---------- 主对话区 ---------- */
.conversation {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-radius: 18px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.58);
  backdrop-filter: blur(18px);
  overflow: hidden;
}

.conv-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 22px;
  border-bottom: 1px solid var(--border-soft);
}
.conv-head h1 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--text);
}
.conv-head p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--muted);
}
.conv-badge {
  flex-shrink: 0;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(124, 58, 237, 0.24);
  background: rgba(124, 58, 237, 0.1);
  color: #6d28d9;
  font-size: 11px;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 22px 24px 12px;
  scroll-behavior: smooth;
}

.hero { max-width: 620px; margin: 6vh auto 0; text-align: center; }
.hero h2 {
  margin: 0 0 8px;
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.02em;
  background: linear-gradient(120deg, #4c1d95, #7c3aed 60%, #db2777);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.hero p { margin: 0 0 22px; font-size: 13px; color: var(--muted); }
.suggestions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.suggestions button {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.7);
  color: var(--text-2);
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
}
.suggestions button:hover {
  transform: translateY(-2px);
  border-color: rgba(124, 58, 237, 0.32);
  background: rgba(124, 58, 237, 0.07);
  color: var(--text);
}

.turn {
  display: flex;
  gap: 12px;
  margin-bottom: 22px;
  max-width: 900px;
}
.turn.user { flex-direction: row-reverse; margin-left: auto; }
.avatar {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-2);
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid var(--border);
}
.turn.assistant .avatar {
  background: linear-gradient(135deg, #7c3aed, #db2777);
  border-color: transparent;
  color: #fff;
}
.bubble-col { min-width: 0; flex: 1; }
.turn.user .bubble-col { flex: 0 1 auto; display: flex; flex-direction: column; align-items: flex-end; }

.bubble {
  display: inline-block;
  max-width: 100%;
  padding: 12px 16px;
  border-radius: 14px;
  border: 1px solid var(--border-soft);
  background: rgba(255, 255, 255, 0.7);
  font-size: 13.5px;
  line-height: 1.75;
  color: var(--text-2);
  overflow-wrap: anywhere;
}
.turn.assistant .bubble { background: transparent; border-color: transparent; padding: 2px 0; }
.turn.user .bubble {
  background: rgba(124, 58, 237, 0.1);
  border-color: rgba(124, 58, 237, 0.22);
  color: var(--text);
}
.user-text { margin: 0; white-space: pre-wrap; }

.caret {
  display: inline-block;
  width: 7px;
  height: 15px;
  margin-left: 2px;
  vertical-align: -2px;
  background: var(--primary);
  animation: blink 1s steps(2, start) infinite;
}
@keyframes blink { 50% { opacity: 0; } }

.cite-box { margin-top: 10px; }
.cite-head {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.7);
  color: var(--muted);
  font-size: 11.5px;
  cursor: pointer;
  transition: all 0.2s ease;
}
.cite-head:hover { color: var(--text); border-color: rgba(124, 58, 237, 0.35); }
.chev { transition: transform 0.2s ease; }
.chev.open { transform: rotate(180deg); }
.cite-list {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}
.cite-list li {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-soft);
  background: rgba(255, 255, 255, 0.55);
}
.cite-idx { flex-shrink: 0; font-size: 11px; color: var(--primary); }
.cite-body { min-width: 0; }
.cite-src { margin: 0 0 4px; font-size: 11.5px; color: var(--text-2); }
.cite-quote {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--muted);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.msg-actions {
  display: flex;
  gap: 14px;
  margin-top: 8px;
  opacity: 0;
  transition: opacity 0.18s ease;
}
.turn:hover .msg-actions { opacity: 1; }
.msg-actions button {
  padding: 0;
  border: 0;
  background: none;
  color: var(--muted-2);
  font-size: 11.5px;
  cursor: pointer;
  transition: color 0.18s ease;
}
.msg-actions button:hover { color: var(--primary); }
.msg-actions button.on { color: #db2777; }

.status-line {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px 42px;
  font-size: 12px;
  color: var(--muted);
}
.status-line .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
  box-shadow: 0 0 10px rgba(124, 58, 237, 0.6);
  animation: pulse 1.2s ease-in-out infinite;
}
@keyframes pulse { 50% { opacity: 0.25; transform: scale(0.8); } }

.to-bottom {
  position: absolute;
  left: 50%;
  bottom: 118px;
  transform: translateX(-50%);
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.92);
  color: var(--text-2);
  font-size: 11.5px;
  cursor: pointer;
  backdrop-filter: blur(12px);
}
.to-bottom:hover { color: var(--primary); border-color: rgba(124, 58, 237, 0.4); }

/* ---------- 输入区 ---------- */
.composer { padding: 10px 22px 16px; }
.composer-box {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 8px 8px 8px 14px;
  border-radius: 14px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.85);
  transition: all 0.2s ease;
}
.composer-box:focus-within {
  border-color: rgba(124, 58, 237, 0.5);
  box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.12), 0 0 22px rgba(124, 58, 237, 0.14);
}
.composer-box textarea {
  flex: 1;
  min-height: 24px;
  max-height: 160px;
  padding: 6px 0;
  border: 0;
  outline: none;
  resize: none;
  background: transparent;
  color: var(--text);
  font-family: inherit;
  font-size: 13.5px;
  line-height: 1.6;
}
.composer-box textarea::placeholder { color: #9a92b3; }
.send {
  flex-shrink: 0;
  height: 36px;
  padding: 0 18px;
  border: 0;
  border-radius: 10px;
  background: var(--primary-grad);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}
.send:hover:not(:disabled) { transform: translateY(-1px); filter: brightness(1.08); }
.send:disabled { opacity: 0.42; cursor: not-allowed; }
.send.stop { background: rgba(225, 29, 72, 0.12); border: 1px solid rgba(225, 29, 72, 0.32); color: #be123c; }
.composer-tip {
  margin: 8px 2px 0;
  font-size: 11px;
  color: var(--muted-2);
  text-align: center;
}

.bubble :deep(.markdown-body) { color: inherit; }
.bubble :deep(pre) {
  background: rgba(124, 58, 237, 0.06);
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  padding: 10px 12px;
  overflow-x: auto;
}
.bubble :deep(code) { font-size: 12.5px; }

@media (max-width: 960px) {
  .chat-page { grid-template-columns: 1fr; height: auto; }
  .thread-rail { max-height: 200px; }
  .messages { padding: 16px; }
  .suggestions { grid-template-columns: 1fr; }
}
</style>
