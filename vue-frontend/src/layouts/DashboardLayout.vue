<template>
  <el-container class="app-layout">
    <el-aside width="268px" class="aside">
      <div class="brand">
        <div class="brand-mark">AI</div>
        <div>
          <div class="brand-name">高校课程AI学习助手</div>
          <div class="brand-sub">课程 RAG 智能平台</div>
        </div>
      </div>

      <el-menu router :default-active="$route.path" background-color="transparent" text-color="#cbd5e1" active-text-color="#ffffff">
        <el-menu-item index="/courses">我的课程</el-menu-item>
        <template v-if="auth.isTeacher">
          <el-menu-item index="/documents">课程知识库</el-menu-item>
        </template>
        <el-menu-item index="/chat">AI 问答</el-menu-item>
        <el-menu-item index="/learning-plan">学习计划</el-menu-item>
        <el-menu-item index="/quiz">自动出题</el-menu-item>
        <template v-if="auth.isTeacher">
          <el-menu-item index="/retrieval-debug">检索可视化</el-menu-item>
          <el-menu-item index="/analytics">问答分析</el-menu-item>
          <el-menu-item index="/dashboard">课程看板</el-menu-item>
        </template>
      </el-menu>

      <div class="aside-footer">
        <el-button class="logout-btn" size="small" type="danger" plain @click="logout">退出登录</el-button>
      </div>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div>
          <div class="top-title">{{ $route.meta.title || '高校课程AI学习助手平台项目' }}</div>
          <div class="course-line" v-if="auth.currentCourseId">当前课程：{{ auth.currentCourseName }} ｜ 课程角色：{{ roleLabel(auth.currentCourseRole) }}</div>
          <div class="course-line" v-else>{{ auth.isTeacher ? '请先进入“我的课程”创建或选择课程' : '请先进入“我的课程”选择已加入的课程' }}</div>
        </div>
        <el-button type="primary" @click="newThread">新建会话</el-button>
      </el-header>
      <el-main class="main"><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { authApi } from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

function newThread() {
  auth.newThread()
  ElMessage.success('已创建新会话')
  router.push('/chat')
}

function roleLabel(role) {
  const map = { teacher: '教师', student: '学生', assistant: '助教', admin: '管理员' }
  return map[role] || '未知'
}

async function logout() {
  try {
    if (auth.refreshToken) await authApi.logout(auth.refreshToken)
  } finally {
    auth.clearAuth()
    router.push('/login')
  }
}
</script>

<style scoped>
.app-layout { min-height: 100vh; }
.aside { padding: 22px 14px; background: rgba(15,23,42,.95); border-right: 1px solid rgba(255,255,255,.08); display: flex; flex-direction: column; }
.brand { display: flex; gap: 12px; align-items: center; padding: 8px 10px 26px; }
.brand-mark { width: 44px; height: 44px; border-radius: 15px; display: grid; place-items: center; background: linear-gradient(135deg,#3b82f6,#06b6d4); font-weight: 900; box-shadow: 0 12px 26px rgba(37,99,235,.30); }
.brand-name { font-weight: 900; color: #fff; }
.brand-sub { font-size: 12px; color: #94a3b8; margin-top: 3px; }
:deep(.el-menu) { border-right: 0; display: grid; gap: 6px; }
:deep(.el-menu-item) { height: 48px; line-height: 48px; border-radius: 14px; margin: 0; padding-left: 18px !important; font-weight: 800; letter-spacing: .01em; transition: .18s ease; }
:deep(.el-menu-item:hover) { background: rgba(59,130,246,.12); color: #fff; }
:deep(.el-menu-item.is-active) { background: linear-gradient(135deg, rgba(37,99,235,.95), rgba(14,165,233,.82)); box-shadow: 0 12px 28px rgba(37,99,235,.28); color: #fff; }
.aside-footer { margin-top: auto; padding: 0 10px; display: grid; gap: 10px; }
.logout-btn { width: 100%; }
.topbar { height: 82px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,.08); background: rgba(15,23,42,.66); backdrop-filter: blur(16px); padding: 0 28px; }
.top-title { color: #fff; font-size: 21px; font-weight: 900; }
.course-line { color: #94a3b8; margin-top: 5px; font-size: 13px; }
.main { padding: 30px; }
@media (max-width: 900px) { .aside { display:none; } .main { padding: 18px; } }
</style>
