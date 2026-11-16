<template>
  <div class="auth-page">
    <!-- 全页共享背景层：光晕、网格、轨道、数据流、粒子 -->
    <div class="bg-layer" aria-hidden="true">
      <div class="bg-grid"></div>
      <div class="glow glow-violet"></div>
      <div class="glow glow-blue"></div>
      <div class="glow glow-pink"></div>
      <div class="ring ring-lg"></div>
      <div class="ring ring-md"></div>
      <div class="ring-arc"></div>
      <svg class="flow" viewBox="0 0 1440 900" preserveAspectRatio="none">
        <defs>
          <linearGradient id="flowGrad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#8b5cf6" stop-opacity="0" />
            <stop offset=".45" stop-color="#a78bfa" stop-opacity=".5" />
            <stop offset="1" stop-color="#ec4899" stop-opacity="0" />
          </linearGradient>
        </defs>
        <path class="flow-line" d="M-40 730 C 240 650, 380 520, 640 570 S 1000 770, 1220 620" />
        <path class="flow-line flow-line-2" d="M80 130 C 340 220, 520 170, 780 270 S 1100 210, 1460 330" />
        <path class="flow-line flow-line-3" d="M560 -30 C 600 160, 790 250, 920 390 S 980 640, 1140 780" />
      </svg>
      <span class="particle particle-1"></span>
      <span class="particle particle-2"></span>
      <span class="particle particle-3"></span>
      <span class="particle particle-4"></span>
      <span class="particle particle-5"></span>
      <span class="particle particle-6"></span>
      <div class="vignette"></div>
    </div>

    <main class="auth-shell">
      <!-- 左侧：主视觉与平台能力 -->
      <section class="showcase">
        <div class="eyebrow"><span class="eyebrow-dot"></span>AI 驱动的课程学习与教学分析平台</div>
        <h1>高校课程 <span class="title-accent">AI 学习助手</span> 平台</h1>
        <p class="subtitle">课程知识管理、智能检索、学习分析与 AI 助手，统一在一个平台完成。</p>

        <div class="capability-field">
          <svg class="network" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="netGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" stop-color="#8b5cf6" stop-opacity=".72" />
                <stop offset=".5" stop-color="#38bdf8" stop-opacity=".42" />
                <stop offset="1" stop-color="#ec4899" stop-opacity=".66" />
              </linearGradient>
            </defs>
            <path d="M16 26 C 30 18, 38 20, 50 24" vector-effect="non-scaling-stroke" />
            <path d="M50 24 C 64 18, 72 22, 84 28" vector-effect="non-scaling-stroke" />
            <path d="M16 34 C 18 52, 20 64, 22 74" vector-effect="non-scaling-stroke" />
            <path d="M50 32 C 50 50, 52 62, 54 74" vector-effect="non-scaling-stroke" />
            <path d="M84 36 C 84 52, 86 64, 88 74" vector-effect="non-scaling-stroke" />
          </svg>

          <article
            v-for="(cap, index) in capabilities"
            :key="cap.title"
            class="capability"
            :style="{ '--i': index }"
          >
            <span class="cap-icon">
              <el-icon><component :is="cap.icon" /></el-icon>
            </span>
            <div class="cap-text">
              <h3>{{ cap.title }}</h3>
              <p>{{ cap.desc }}</p>
            </div>
          </article>
        </div>

        <div class="stat-strip">
          <div v-for="stat in stats" :key="stat.label" class="stat-card">
            <span class="stat-value">{{ stat.value }}</span>
            <span class="stat-label">{{ stat.label }}</span>
          </div>
        </div>
      </section>

      <!-- 右侧：轻量玻璃登录面板 -->
      <aside class="login-panel">
        <div class="panel-aura" aria-hidden="true"></div>

        <transition name="swap" mode="out-in">
          <div v-if="mode === 'login'" key="login" class="panel-inner">
            <h2>欢迎回来</h2>
            <p class="panel-desc">登录后继续你的课程学习与 AI 助手任务。</p>

            <el-form ref="loginRef" :model="loginForm" :rules="loginRules" label-position="top" class="auth-form" @submit.prevent>
              <el-form-item label="账号" prop="username">
                <el-input v-model="loginForm.username" placeholder="请输入账号" autocomplete="username">
                  <template #prefix><el-icon><User /></el-icon></template>
                </el-input>
              </el-form-item>
              <el-form-item label="密码" prop="password">
                <el-input
                  v-model="loginForm.password"
                  :type="showPwd ? 'text' : 'password'"
                  placeholder="请输入密码"
                  autocomplete="current-password"
                >
                  <template #prefix><el-icon><Lock /></el-icon></template>
                  <template #suffix>
                    <el-icon class="pwd-toggle" @click="showPwd = !showPwd">
                      <View v-if="!showPwd" />
                      <Hide v-else />
                    </el-icon>
                  </template>
                </el-input>
              </el-form-item>
              <el-button type="primary" class="submit-btn" :loading="loading" @click="login">登录</el-button>
            </el-form>

            <div class="panel-links">
              <button type="button" @click="mode = 'register'">注册账号</button>
              <span class="link-divider"></span>
              <button type="button" @click="forgotPassword">忘记密码</button>
            </div>
          </div>

          <div v-else key="register" class="panel-inner">
            <h2>创建账号</h2>
            <p class="panel-desc">注册后即可加入课程并使用 AI 助手。</p>

            <el-form ref="registerRef" :model="registerForm" :rules="registerRules" label-position="top" class="auth-form" @submit.prevent>
              <el-form-item label="账号" prop="username">
                <el-input v-model="registerForm.username" placeholder="设置登录账号" autocomplete="username">
                  <template #prefix><el-icon><User /></el-icon></template>
                </el-input>
              </el-form-item>
              <el-form-item label="密码" prop="password">
                <el-input v-model="registerForm.password" type="password" placeholder="至少 8 个字符" show-password autocomplete="new-password">
                  <template #prefix><el-icon><Lock /></el-icon></template>
                </el-input>
              </el-form-item>
              <el-form-item label="确认密码" prop="confirmPassword">
                <el-input v-model="registerForm.confirmPassword" type="password" placeholder="再次输入密码" show-password autocomplete="new-password">
                  <template #prefix><el-icon><Lock /></el-icon></template>
                </el-input>
              </el-form-item>
              <el-form-item label="身份" prop="role">
                <el-radio-group v-model="registerForm.role" class="role-selector" @change="registerRef?.clearValidate('teacherInviteCode')">
                  <el-radio-button label="student">学生</el-radio-button>
                  <el-radio-button label="teacher">教师</el-radio-button>
                </el-radio-group>
                <div class="role-tip">学生用于学习与问答；教师需填写邀请码，可创建课程并查看分析。</div>
              </el-form-item>
              <el-form-item v-if="registerForm.role === 'teacher'" label="教师邀请码" prop="teacherInviteCode">
                <el-input v-model="registerForm.teacherInviteCode" placeholder="请输入教师邀请码" autocomplete="off">
                  <template #prefix><el-icon><Key /></el-icon></template>
                </el-input>
              </el-form-item>
              <el-button type="primary" class="submit-btn" :loading="loading" @click="register">注册并登录</el-button>
            </el-form>

            <div class="panel-links">
              <button type="button" @click="mode = 'login'">返回登录</button>
            </div>
          </div>
        </transition>
      </aside>
    </main>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Hide, Histogram, Key, Link, Lock, MagicStick, Reading, Search, TrendCharts, User, View
} from '@element-plus/icons-vue'
import { authApi, threadApi } from '../api'
import { errorMessage } from '../api/request'
import { useAuthStore } from '../stores/auth'
import { v4Like } from '../utils/id'

const router = useRouter()
const auth = useAuthStore()
const mode = ref('login')
const showPwd = ref(false)
const loading = ref(false)
const loginRef = ref()
const registerRef = ref()
const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', password: '', confirmPassword: '', role: 'student', teacherInviteCode: '' })

const capabilities = [
  { icon: Reading, title: '课程知识库', desc: '课程资料统一入库' },
  { icon: Search, title: '智能检索', desc: '向量与关键词混合召回' },
  { icon: Link, title: '引用溯源', desc: '回答附带原文出处' },
  { icon: MagicStick, title: '学习 Agent', desc: '多轮问答与学习规划' },
  { icon: TrendCharts, title: '教师分析', desc: '问答质量与学情洞察' },
  { icon: Histogram, title: '学习数据看板', desc: '学习行为实时可视化' }
]

const stats = [
  { label: '课程数', value: '128' },
  { label: '学习记录', value: '35,620' },
  { label: 'AI 问答', value: '8,940' },
  { label: '教师分析', value: '36' }
]

const loginRules = {
  username: [
    { required: true, message: '请输入账号', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_]{3,32}$/, message: '账号只能包含英文、数字、下划线，长度 3-32 位', trigger: 'blur' }
  ],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}
const registerRules = {
  username: [
    { required: true, message: '请输入账号', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_]{3,32}$/, message: '账号只能包含英文、数字、下划线，长度 3-32 位', trigger: 'blur' }
  ],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 8, message: '密码至少需要 8 个字符', trigger: 'blur' }],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: (_, value, callback) => value !== registerForm.password ? callback(new Error('两次输入的密码不一致')) : callback(), trigger: 'blur' }
  ],
  role: [{ required: true, message: '请选择注册身份', trigger: 'change' }],
  teacherInviteCode: [
    {
      validator: (_, value, callback) => {
        if (registerForm.role === 'teacher' && !String(value || '').trim()) {
          callback(new Error('教师注册需要邀请码'))
          return
        }
        callback()
      },
      trigger: 'blur'
    }
  ]
}

function forgotPassword() {
  ElMessage.info('请联系课程管理员重置密码')
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
    router.push(auth.isAdmin ? '/admin/stats' : '/courses')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally { loading.value = false }
}

async function register() {
  await registerRef.value?.validate()
  loading.value = true
  try {
    const { data } = await authApi.register({
      username: registerForm.username.trim(),
      password: registerForm.password,
      role: registerForm.role,
      teacher_invite_code: registerForm.role === 'teacher' ? registerForm.teacherInviteCode.trim() : ''
    })
    auth.saveAuth(data)
    await restoreLatestThread()
    router.push(auth.isAdmin ? '/admin/stats' : '/courses')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally { loading.value = false }
}
</script>

<style scoped>
/* ============ 页面与共享背景 ============ */
.auth-page {
  position: relative;
  min-height: 100vh;
  min-height: 100dvh;
  display: grid;
  place-items: start center;
  overflow: hidden;
  padding: clamp(40px, 8vh, 96px) clamp(20px, 4vw, 64px) clamp(28px, 5vh, 64px);
  background:
    radial-gradient(56% 52% at 48% 32%, rgba(108, 78, 196, 0.4), transparent 70%),
    radial-gradient(46% 44% at 2% -4%, rgba(139, 92, 246, 0.6), transparent 62%),
    radial-gradient(42% 40% at 100% -2%, rgba(72, 132, 255, 0.4), transparent 64%),
    radial-gradient(48% 46% at 84% 102%, rgba(236, 72, 153, 0.42), transparent 68%),
    radial-gradient(40% 42% at 12% 100%, rgba(56, 189, 248, 0.24), transparent 66%),
    linear-gradient(152deg, #141539 0%, #1b1342 34%, #14102f 64%, #0a0c24 100%);
}

.bg-layer { position: absolute; inset: 0; overflow: hidden; pointer-events: none; }

/* 科技网格：中心亮、边缘淡出 */
.bg-grid {
  position: absolute;
  inset: -1px;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.065) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.065) 1px, transparent 1px);
  background-size: 64px 64px;
  -webkit-mask-image: radial-gradient(88% 84% at 46% 40%, #000 26%, transparent 86%);
  mask-image: radial-gradient(88% 84% at 46% 40%, #000 26%, transparent 86%);
  opacity: 0.95;
}

.glow { position: absolute; border-radius: 50%; filter: blur(10px); }
.glow-violet {
  width: 780px; height: 780px; left: -230px; top: -230px;
  background: radial-gradient(circle, rgba(139, 92, 246, 0.56), transparent 68%);
}
.glow-blue {
  width: 620px; height: 620px; right: 2%; top: -12%;
  background: radial-gradient(circle, rgba(56, 132, 255, 0.38), transparent 70%);
}
.glow-pink {
  width: 820px; height: 820px; right: 6%; bottom: -38%;
  background: radial-gradient(circle, rgba(236, 72, 153, 0.42), transparent 68%);
}

/* 半透明圆环与弧形轨道 */
.ring { position: absolute; border-radius: 50%; border: 1px solid rgba(167, 139, 250, 0.13); }
.ring-lg { width: min(1020px, 96vw); aspect-ratio: 1; right: -20%; top: -34%; }
.ring-md {
  width: min(660px, 62vw); aspect-ratio: 1; right: -4%; top: -14%;
  border-style: dashed; border-color: rgba(196, 181, 253, 0.1);
}
.ring-arc {
  position: absolute;
  width: min(1100px, 110vw); aspect-ratio: 1;
  left: -46%; bottom: -62%;
  border-radius: 50%;
  background: conic-gradient(from 128deg, transparent 0 52%, rgba(236, 72, 153, 0.3) 64%, rgba(139, 92, 246, 0.24) 72%, transparent 80%);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 1.5px), #000 calc(100% - 1px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 1.5px), #000 calc(100% - 1px));
  opacity: 0.8;
}

/* 数据流线 */
.flow { position: absolute; inset: 0; width: 100%; height: 100%; }
.flow-line {
  fill: none;
  stroke: url(#flowGrad);
  stroke-width: 1.2;
  stroke-linecap: round;
  stroke-dasharray: 2 14;
  animation: flowDash 22s linear infinite;
}
.flow-line-2 { animation-duration: 28s; animation-direction: reverse; opacity: 0.7; }
.flow-line-3 { animation-duration: 34s; opacity: 0.55; }

/* 粒子光点 */
.particle {
  position: absolute;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #ddd6fe;
  box-shadow: 0 0 10px 2px rgba(167, 139, 250, 0.65);
  animation: floatDot 9s ease-in-out infinite;
}
.particle-1 { left: 18%; top: 26%; animation-delay: -1s; }
.particle-2 { left: 41%; top: 12%; animation-delay: -3s; }
.particle-3 { left: 8%; top: 68%; animation-delay: -5s; }
.particle-4 { left: 62%; top: 78%; animation-delay: -2s; width: 2px; height: 2px; }
.particle-5 { left: 88%; top: 32%; animation-delay: -6s; }
.particle-6 { left: 74%; top: 8%; animation-delay: -4s; width: 2px; height: 2px; }

.vignette {
  position: absolute;
  inset: 0;
  background: radial-gradient(120% 100% at 50% 42%, transparent 44%, rgba(5, 5, 18, 0.6) 100%);
}

/* ============ 布局骨架 ============ */
.auth-shell {
  position: relative;
  z-index: 2;
  width: min(1400px, 100%);
  min-height: calc(100dvh - clamp(40px, 8vh, 96px) - clamp(28px, 5vh, 64px));
  display: grid;
  grid-template-columns: minmax(0, 1.85fr) minmax(300px, 1fr);
  align-items: center;
  gap: clamp(40px, 5vw, 96px);
}

.showcase { display: flex; flex-direction: column; align-self: start; }

.eyebrow {
  display: inline-flex;
  align-self: flex-start;
  align-items: center;
  gap: 8px;
  padding: 7px 14px;
  border-radius: 999px;
  background: rgba(139, 92, 246, 0.12);
  border: 1px solid rgba(167, 139, 250, 0.26);
  color: #ddd6fe;
  font-size: 12px;
  letter-spacing: 0.06em;
  animation: fadeUp 0.7s 0.05s both;
}
.eyebrow-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #c4b5fd;
  box-shadow: 0 0 8px rgba(196, 181, 253, 0.9);
}

h1 {
  margin: 20px 0 12px;
  font-size: clamp(40px, 4.2vw, 60px);
  line-height: 1.14;
  letter-spacing: -0.045em;
  font-weight: 800;
  background: linear-gradient(180deg, #ffffff 10%, #ecdfff 62%, #c4b5fd 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: fadeUp 0.8s 0.12s both;
}
.title-accent {
  background: linear-gradient(100deg, #c4b5fd, #f0abfc 55%, #f9a8d4);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.subtitle {
  max-width: 560px;
  margin: 0;
  color: rgba(255, 255, 255, 0.7);
  font-size: 15px;
  line-height: 1.85;
  animation: fadeUp 0.8s 0.2s both;
}

/* ============ 能力网络 ============ */
.capability-field {
  position: relative;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: clamp(22px, 2.6vw, 32px);
  padding: 4px 0;
}

.network {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
  pointer-events: none;
  z-index: 0;
}
.network path {
  fill: none;
  stroke: url(#netGrad);
  stroke-width: 1.2;
  stroke-dasharray: 4 7;
  animation: networkFlow 16s linear infinite;
}

.capability {
  --shift: 0px;
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(46, 38, 88, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  transform: translateY(var(--shift));
  transition: all 0.2s ease;
  animation: moduleIn 0.7s cubic-bezier(0.22, 0.61, 0.36, 1) both;
  animation-delay: calc(0.3s + var(--i) * 0.07s);
}
.capability:hover {
  transform: translateY(-3px);
  background: rgba(64, 52, 116, 0.42);
  border-color: rgba(196, 181, 253, 0.42);
  box-shadow: 0 18px 40px -24px rgba(139, 92, 246, 0.9);
}

.cap-icon {
  flex: none;
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 9px;
  background: linear-gradient(150deg, rgba(139, 92, 246, 0.42), rgba(236, 72, 153, 0.26));
  border: 1px solid rgba(255, 255, 255, 0.18);
  color: #f3e8ff;
  font-size: 16px;
}
.cap-text h3 {
  margin: 1px 0 3px;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  letter-spacing: -0.01em;
}
.cap-text p {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(255, 255, 255, 0.62);
}

/* ============ 数据预览 ============ */
.stat-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-top: clamp(16px, 2vw, 24px);
  padding: 8px 6px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.035);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  animation: fadeUp 0.8s 0.5s both;
}
.stat-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 2px 16px;
  border-radius: 8px;
  transition: all 0.2s ease;
}
.stat-card + .stat-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 1px;
  height: 26px;
  background: rgba(255, 255, 255, 0.1);
}
.stat-card:hover { background: rgba(255, 255, 255, 0.05); }
.stat-value {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.02em;
  background: linear-gradient(180deg, #fff, #d8c9ff);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.stat-label { font-size: 11px; color: rgba(255, 255, 255, 0.58); }

/* ============ 登录面板 ============ */
.login-panel {
  position: relative;
  justify-self: center;
  align-self: center;
  width: min(100%, 340px);
  padding: clamp(22px, 2vw, 26px);
  border-radius: 12px;
  background: linear-gradient(155deg, rgba(58, 47, 106, 0.36), rgba(26, 21, 52, 0.28));
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 40px 90px -34px rgba(0, 0, 0, 0.92), 0 0 46px -22px rgba(139, 92, 246, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.09);
  backdrop-filter: blur(22px) saturate(130%);
  -webkit-backdrop-filter: blur(22px) saturate(130%);
  overflow: hidden;
  animation: fadeUp 0.9s 0.28s both;
}
.login-panel::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(196, 181, 253, 0.55), transparent);
}
.panel-aura {
  position: absolute;
  width: 300px;
  height: 300px;
  right: -130px;
  top: -150px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(236, 72, 153, 0.2), transparent 70%);
  pointer-events: none;
}
.panel-inner { position: relative; z-index: 1; }

.panel-inner h2 {
  margin: 0 0 6px;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #fff;
}
.panel-desc {
  margin: 0 0 18px;
  font-size: 12.5px;
  line-height: 1.65;
  color: rgba(255, 255, 255, 0.68);
}

.auth-form :deep(.el-form-item) { margin-bottom: 14px; }
.auth-form :deep(.el-input__wrapper) { min-height: 44px; }
.auth-form :deep(.el-form-item__label) {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.74) !important;
}
.auth-form :deep(.el-input__inner::placeholder) { color: rgba(255, 255, 255, 0.48) !important; }
.auth-form :deep(.el-input__prefix),
.auth-form :deep(.el-input__suffix) { color: rgba(255, 255, 255, 0.62) !important; }
.auth-form :deep(.el-form-item:last-of-type) { margin-bottom: 18px; }

.pwd-toggle { cursor: pointer; transition: all 0.2s ease; }
.pwd-toggle:hover { color: #e9d5ff; }
.pwd-toggle:focus-visible { outline: 2px solid rgba(167, 139, 250, 0.7); outline-offset: 2px; border-radius: 4px; }

.submit-btn {
  width: 100%;
  height: 44px;
  min-height: 44px;
  font-size: 15px;
  letter-spacing: 0.02em;
}

.panel-links {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 14px;
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.62);
}
.panel-links button {
  padding: 2px 4px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
  transition: all 0.2s ease;
  border-radius: 6px;
}
.panel-links button:hover { color: #f0abfc; }
.panel-links button:focus-visible { outline: 2px solid rgba(167, 139, 250, 0.7); outline-offset: 2px; }
.link-divider { width: 1px; height: 12px; background: rgba(255, 255, 255, 0.16); }

.role-selector { width: 100%; display: grid; grid-template-columns: 1fr 1fr; }
.role-selector :deep(.el-radio-button__inner) { width: 100%; font-weight: 600; }
.role-tip { margin-top: 8px; color: rgba(255, 255, 255, 0.42); font-size: 11.5px; line-height: 1.6; }

/* 登录 / 注册切换过渡 */
.swap-enter-active,
.swap-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.swap-enter-from { opacity: 0; transform: translateY(8px); }
.swap-leave-to { opacity: 0; transform: translateY(-8px); }

/* ============ 动效 ============ */
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(18px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes moduleIn {
  from { opacity: 0; transform: translateY(calc(var(--shift) + 16px)); }
  to { opacity: 1; transform: translateY(var(--shift)); }
}
@keyframes flowDash {
  from { stroke-dashoffset: 0; }
  to { stroke-dashoffset: -320; }
}
@keyframes networkFlow {
  from { stroke-dashoffset: 0; }
  to { stroke-dashoffset: -120; }
}
@keyframes floatDot {
  0%, 100% { transform: translate3d(0, 0, 0); opacity: 0.32; }
  50% { transform: translate3d(6px, -18px, 0); opacity: 0.95; }
}

/* ============ 响应式 ============ */
@media (max-width: 1180px) {
  .auth-shell { grid-template-columns: 1fr; min-height: auto; gap: 32px; }
  .login-panel { justify-self: center; width: min(100%, 380px); }
  .showcase { width: 100%; }
}

@media (max-width: 860px) {
  h1 { font-size: 36px; }
}

@media (max-width: 560px) {
  .auth-page { padding: 22px 14px 26px; }
  .eyebrow { font-size: 11px; padding: 6px 11px; }
  h1 { margin-top: 16px; font-size: 30px; line-height: 1.2; }
  .subtitle { font-size: 13.5px; line-height: 1.75; }
  .capability-field { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 20px; }
  .network { display: none; }
  .capability { padding: 11px; gap: 9px; }
  .cap-icon { width: 30px; height: 30px; font-size: 14px; }
  .cap-text h3 { font-size: 12.5px; }
  .cap-text p { font-size: 11px; }
  .stat-strip { padding: 8px 4px; margin-top: 18px; }
  .stat-card { padding: 2px 10px; }
  .stat-value { font-size: 16px; }
  .login-panel { padding: 20px 16px; border-radius: 14px; }
  .panel-inner h2 { font-size: 22px; }
  .panel-desc { margin-bottom: 16px; font-size: 12.5px; }
}

@media (prefers-reduced-motion: reduce) {
  .eyebrow, h1, .subtitle, .capability, .stat-strip, .login-panel { animation: none; }
  .flow-line, .network path, .particle { animation: none; }
}
</style>
