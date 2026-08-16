<template>
  <div>
    <h1 class="page-title">AI 问答</h1><p class="page-desc">基于当前课程资料进行带引用问答，支持多轮追问与回答反馈。</p>
    <div v-if="!auth.hasCourse" class="empty-state">请先在“我的课程”里创建或选择一门课程。</div>
    <template v-else>
      <el-card class="chat-card">
        <div v-if="!auth.messages.length" class="empty-state">输入课程相关问题，系统会检索知识库并生成带引用回答。</div>
        <div v-for="(m,i) in auth.messages" :key="i" class="msg" :class="m.role">
          <div class="role">{{ m.role === 'user' ? '我' : 'AI 助手' }}</div>
          <MarkdownRenderer v-if="m.role !== 'user'" :source="m.content" />
          <div v-else>{{ m.content }}</div>
        </div>
      </el-card>
      <el-card v-if="auth.lastQuestion && auth.lastAnswer" class="panel-card feedback">
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
    </template>
  </div>
</template>
<script setup>
import { reactive, ref } from 'vue'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import { ElMessage } from 'element-plus'
import { courseApi } from '../api'
import { errorMessage } from '../api/request'
import { useAuthStore } from '../stores/auth'
const auth=useAuthStore(); const question=ref(''); const asking=ref(false); const reasons=['答案不准确','没有引用','引用不相关','回答太少','没看懂','其他']; const down=reactive({reason:'答案不准确',comment:''})
function withCitations(result){ let txt=String(result.answer ?? JSON.stringify(result)); const cs=result.citations||[]; if(cs.length){ txt+='\n\n#### 引用来源\n'+cs.map(c=>`- ${c.source_name||c.source||'未知来源'} ${c.locator||''}: ${c.quote||c.content||''}`).join('\n') } return txt }
async function ask(){ if(!question.value.trim()) return; const q=question.value.trim(); auth.lastQuestion=q; auth.messages.push({role:'user',content:q}); question.value=''; asking.value=true; try{ const {data}=await courseApi.ask(auth.currentCourseId,{question:q,thread_id:auth.threadId}); const answer=withCitations(data); auth.lastAnswer=answer; auth.messages.push({role:'assistant',content:answer}); auth.persist() }catch(e){ auth.messages.push({role:'assistant',content:`请求失败：${errorMessage(e)}`}); auth.persist() }finally{ asking.value=false } }
async function feedbackUp(){ await courseApi.feedback(auth.currentCourseId,{thread_id:auth.threadId,question:auth.lastQuestion,answer:auth.lastAnswer,rating:'up',reason:'',comment:''}); ElMessage.success('感谢反馈') }
async function feedbackDown(){ await courseApi.feedback(auth.currentCourseId,{thread_id:auth.threadId,question:auth.lastQuestion,answer:auth.lastAnswer,rating:'down',reason:down.reason,comment:down.comment}); ElMessage.success('反馈已记录') }
</script>
<style scoped>
.chat-card {
  max-width: 1180px;
  min-height: 430px;
  margin: 0 auto 16px;
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
  max-width: 1180px;
  margin: 0 auto;
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
  .msg { max-width: 92%; }
  .ask-bar { grid-template-columns: 1fr; }
}
</style>
