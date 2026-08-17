<template>
  <div class="login-page">
    <section class="hero">
      <div class="badge">课程 RAG 智能助手</div>
      <h1>高校课程AI学习助手平台项目</h1>
      <p>面向高校课程资料与教学知识库的 RAG 智能问答平台，覆盖资料入库、引用溯源、多轮问答、学习计划、自动出题和教师分析看板。</p>
      <div class="chips">
        <el-tag effect="plain" round>课程知识库</el-tag>
        <el-tag effect="plain" round>混合检索</el-tag>
        <el-tag effect="plain" round>引用溯源</el-tag>
        <el-tag effect="plain" round>学习 Agent</el-tag>
        <el-tag class="chip-analysis" effect="plain" round>教师分析</el-tag>
      </div>
    </section>

    <el-card class="login-card">
      <h2>账号登录</h2>
      <p>登录后继续管理课程资料和 AI 问答会话。</p>
      <el-tabs v-model="activeTab" class="auth-tabs" stretch>
        <el-tab-pane label="登录" name="login">
          <el-form ref="loginRef" :model="loginForm" :rules="loginRules" label-position="top" @submit.prevent>
            <el-form-item label="用户名" prop="username">
              <el-input v-model="loginForm.username" placeholder="请输入用户名" autocomplete="username" />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input v-model="loginForm.password" type="password" placeholder="请输入密码" show-password autocomplete="current-password" />
            </el-form-item>
            <el-button type="primary" :loading="loading" class="full" @click="login">登录</el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="注册" name="register">
          <el-form ref="registerRef" :model="registerForm" :rules="registerRules" label-position="top" @submit.prevent>
            <el-form-item label="用户名" prop="username">
              <el-input v-model="registerForm.username" placeholder="设置登录用户名" autocomplete="username" />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input v-model="registerForm.password" type="password" placeholder="至少 8 个字符" show-password autocomplete="new-password" />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirmPassword">
              <el-input v-model="registerForm.confirmPassword" type="password" placeholder="再次输入密码" show-password autocomplete="new-password" />
            </el-form-item>
            <el-form-item label="选择身份" prop="role">
              <el-radio-group v-model="registerForm.role" class="role-selector">
                <el-radio-button label="student">学生</el-radio-button>
                <el-radio-button label="teacher">教师</el-radio-button>
              </el-radio-group>
              <div class="role-tip">学生用于课程学习、AI 问答和练习；教师可创建课程、上传资料并查看教学分析。</div>
            </el-form-item>
            <el-button type="primary" :loading="loading" class="full" @click="register">注册并登录</el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authApi, threadApi } from '../api'
import { errorMessage } from '../api/request'
import { useAuthStore } from '../stores/auth'
import { v4Like } from '../utils/id'

const router = useRouter()
const auth = useAuthStore()
const activeTab = ref('login')
const loading = ref(false)
const loginRef = ref()
const registerRef = ref()
const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', password: '', confirmPassword: '', role: 'student' })

const loginRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_]{3,32}$/, message: '用户名只能包含英文、数字、下划线，长度 3-32 位', trigger: 'blur' }
  ],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}
const registerRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_]{3,32}$/, message: '用户名只能包含英文、数字、下划线，长度 3-32 位', trigger: 'blur' }
  ],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 8, message: '密码至少需要 8 个字符', trigger: 'blur' }],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: (_, value, callback) => value !== registerForm.password ? callback(new Error('两次输入的密码不一致')) : callback(), trigger: 'blur' }
  ],
  role: [{ required: true, message: '请选择注册身份', trigger: 'change' }]
}

async function restoreLatestThread() {
  try {
    const { data } = await threadApi.list()
    const threads = data.threads || []
    if (threads.length) {
      const detail = await threadApi.detail(threads[0].thread_id)
      auth.setThread(detail.data.thread_id, detail.data.history || [])
      return
    }
  } catch {}
  auth.setThread(v4Like(), [])
}

async function login() {
  await loginRef.value?.validate()
  loading.value = true
  try {
    const { data } = await authApi.login({ username: loginForm.username.trim(), password: loginForm.password })
    auth.saveAuth(data)
    await restoreLatestThread()
    router.push('/courses')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally { loading.value = false }
}

async function register() {
  await registerRef.value?.validate()
  loading.value = true
  try {
    const { data } = await authApi.register({ username: registerForm.username.trim(), password: registerForm.password, role: registerForm.role })
    auth.saveAuth(data)
    await restoreLatestThread()
    router.push('/courses')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally { loading.value = false }
}
</script>

<style scoped>
.login-page { min-height: 100vh; display: grid; grid-template-columns: .95fr 1.05fr; gap: 34px; align-items: center; padding: clamp(24px, 4vw, 56px); }
.hero { min-height: 520px; display: flex; flex-direction: column; justify-content: center; padding: clamp(42px, 5vw, 64px); border-radius: 32px; background: linear-gradient(135deg,rgba(255,255,255,.98),rgba(239,246,255,.92)); color: #0f172a; box-shadow: var(--shadow); }
.badge { display:inline-flex; padding: 8px 13px; border-radius: 999px; background:#eff6ff; color:#1d4ed8; font-weight:900; border:1px solid #dbeafe; }
h1 { max-width: 820px; margin: 20px 0 14px; font-size: clamp(40px,4.6vw,68px); line-height: 1.04; letter-spacing: -.06em; font-weight: 900; }
p { max-width: 680px; color:#475569; line-height: 1.9; font-size: 17px; }
.chips { display:flex; flex-wrap:wrap; gap:12px; margin:30px 0 0; }
.chips :deep(.el-tag) { height: 34px; padding: 0 14px; border-color: #bfdbfe; background: rgba(239,246,255,.82); color: #1d4ed8; font-weight: 700; font-family: inherit; letter-spacing: 0; }
.chips :deep(.chip-analysis) { min-width: 82px; justify-content: center; }
.login-card { width: min(100%, 560px); justify-self: center; padding: 14px; border-radius: 28px; box-shadow: var(--shadow); }
.login-card h2 { font-size: 30px; margin: 10px 0 6px; color:#0f172a; }
.login-card p { font-size: 14px; margin-bottom: 18px; }
.auth-tabs :deep(.el-tabs__item) { height: 46px; font-weight: 800; color: #64748b; }
.auth-tabs :deep(.el-tabs__item.is-active) { color: #2563eb; }
.auth-tabs :deep(.el-tabs__active-bar) { height: 3px; border-radius: 999px; background: linear-gradient(90deg,#2563eb,#06b6d4); }
.role-selector { width: 100%; display: grid; grid-template-columns: 1fr 1fr; }
.role-selector :deep(.el-radio-button__inner) { width: 100%; font-weight: 800; }
.role-tip { margin-top: 8px; color: #64748b; font-size: 12px; line-height: 1.6; }
.full { width: 100%; margin-top: 8px; }
@media (max-width: 1040px) { .login-page { grid-template-columns:1fr; } .login-card { justify-self: stretch; width: 100%; } }
/* 新增：移动端响应式，仅作用于 <768px，压缩首页留白和标题尺寸，PC 端保持不变 */
@media (max-width: 768px) {
  .login-page {
    min-height: 100dvh;
    align-content: start;
    gap: 14px;
    padding: 14px;
  }

  .hero {
    min-height: auto;
    justify-content: flex-start;
    padding: 22px 18px;
    border-radius: 22px;
  }

  .badge {
    padding: 6px 10px;
    font-size: 12px;
  }

  h1 {
    margin: 14px 0 10px;
    font-size: 31px;
    line-height: 1.14;
    letter-spacing: -.045em;
  }

  p {
    font-size: 14px;
    line-height: 1.7;
  }

  .chips {
    gap: 8px;
    margin-top: 16px;
  }

  .chips :deep(.el-tag) {
    height: 28px;
    padding: 0 10px;
    font-size: 12px;
  }

  .chips :deep(.chip-analysis) {
    min-width: auto;
  }

  .login-card {
    padding: 4px;
    border-radius: 22px;
  }

  .login-card h2 {
    margin-top: 4px;
    font-size: 24px;
  }

  .login-card p {
    margin-bottom: 12px;
    font-size: 13px;
  }

  .auth-tabs :deep(.el-tabs__item) {
    height: 40px;
    font-size: 14px;
  }

  .role-tip {
    font-size: 11px;
  }
}

@media (max-width: 420px) {
  .login-page {
    padding: 10px;
  }

  .hero {
    padding: 18px 14px;
    border-radius: 18px;
  }

  h1 {
    font-size: 28px;
  }
}
</style>
