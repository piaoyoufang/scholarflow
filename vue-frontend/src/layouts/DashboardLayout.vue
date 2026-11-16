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
        <template v-if="auth.isAdmin">
          <el-menu-item index="/admin/stats">数据统计</el-menu-item>
          <el-menu-item index="/admin/accounts">账号管理</el-menu-item>
          <el-menu-item index="/admin/courses">课程管理</el-menu-item>
          <el-menu-item index="/admin/invites">教师邀请码</el-menu-item>
        </template>
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
        <el-button class="mobile-menu-btn" type="primary" plain @click="mobileMenuVisible = true">菜单</el-button>
        <div class="topbar-title-block">
          <div class="top-title">{{ $route.meta.title || '高校课程AI学习助手平台项目' }}</div>
          <div class="course-line" v-if="auth.currentCourseId">当前课程：{{ auth.currentCourseName }} ｜ 课程角色：{{ roleLabel(auth.currentCourseRole) }}</div>
          <div class="course-line" v-else>{{ auth.isAdmin ? '管理员工作台：账号、课程与全平台数据统计' : (auth.isTeacher ? '请先进入“我的课程”创建或选择课程' : '请先进入“我的课程”选择已加入的课程') }}</div>
        </div>
      </el-header>
      <el-main class="main"><router-view /></el-main>
    </el-container>

    <el-drawer v-model="mobileMenuVisible" title="高校课程AI学习助手" direction="ltr" size="78%" class="mobile-drawer">
      <el-menu router :default-active="$route.path" background-color="transparent" text-color="#cbd5e1" active-text-color="#ffffff" @select="mobileMenuVisible = false">
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
        <el-menu-item v-if="auth.isAdmin" index="/admin/stats">数据统计</el-menu-item>
        <el-menu-item v-if="auth.isAdmin" index="/admin/accounts">账号管理</el-menu-item>
        <el-menu-item v-if="auth.isAdmin" index="/admin/courses">课程管理</el-menu-item>
        <el-menu-item v-if="auth.isAdmin" index="/admin/invites">教师邀请码</el-menu-item>
      </el-menu>
      <el-button class="mobile-logout" type="danger" plain @click="logout">退出登录</el-button>
    </el-drawer>
  </el-container>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const mobileMenuVisible = ref(false)

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
.aside { padding: 22px 14px; background: rgba(255,255,255,.055); border-right: 1px solid rgba(255,255,255,.11); backdrop-filter: blur(22px); -webkit-backdrop-filter: blur(22px); display: flex; flex-direction: column; }
.brand { display: flex; gap: 12px; align-items: center; padding: 8px 10px 22px; }
.brand-mark { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; background: linear-gradient(140deg,#a78bfa,#ec4899); font-weight: 800; font-size: 12px; color: #fff; box-shadow: 0 10px 26px -12px rgba(236,72,153,.9); }
.brand-name { font-weight: 700; color: #fff; font-size: 14px; letter-spacing: -.01em; }
.brand-sub { font-size: 11px; color: rgba(255,255,255,.5); margin-top: 3px; }
:deep(.el-menu) { border-right: 0; display: grid; gap: 3px; background: transparent !important; }
:deep(.el-menu-item) { height: 40px; line-height: 40px; border-radius: 10px; margin: 0; padding-left: 14px !important; font-weight: 500; font-size: 13px; color: rgba(255,255,255,.74) !important; border: 1px solid transparent; transition: .18s ease; }
:deep(.el-menu-item:hover) { background: rgba(255,255,255,.09) !important; color: #fff !important; }
:deep(.el-menu-item.is-active) { background: rgba(255,255,255,.16) !important; border-color: rgba(255,255,255,.24); box-shadow: 0 10px 26px -18px rgba(255,255,255,.65); color: #fff !important; font-weight: 600; }
.aside-footer { margin-top: auto; padding: 0 6px; display: grid; gap: 10px; }
.logout-btn { width: 100%; }
.topbar { height: 62px; display: flex; align-items: center; justify-content: space-between; gap: 14px; border-bottom: 1px solid rgba(255,255,255,.1); background: rgba(255,255,255,.05); backdrop-filter: blur(22px); -webkit-backdrop-filter: blur(22px); padding: 0 26px; }
.mobile-menu-btn { display: none; flex: 0 0 auto; }
.topbar-title-block { min-width: 0; }
.top-title { color: #fff; font-size: 16px; font-weight: 700; letter-spacing: -.01em; }
.course-line { color: rgba(255,255,255,.55); margin-top: 4px; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.main { padding: 26px 28px 60px; }
.mobile-logout { width: 100%; margin-top: 18px; }
:global(.mobile-drawer .el-drawer__body) { background: rgba(18,12,30,.98); padding: 14px; }
:global(.mobile-drawer .el-drawer__header) { margin-bottom: 0; padding: 18px; background: rgba(18,12,30,.98); color: #fff; }
:global(.mobile-drawer .el-menu) { border-right: 0; background: transparent !important; }
:global(.mobile-drawer .el-menu-item) { border-radius: 10px; margin-bottom: 4px; font-weight: 500; color: rgba(255,255,255,.75); }
:global(.mobile-drawer .el-menu-item.is-active) { background: rgba(255,255,255,.16); color: #fff; }
@media (max-width: 900px) {
  .aside { display:none; }
  /* 新增：移动端响应式，避免全局按钮 100% 宽度把顶部撑高 */
  .mobile-menu-btn {
    display: inline-flex;
    width: auto !important;
    min-width: 72px;
    height: 36px;
    min-height: 36px;
    padding: 0 14px;
    flex: 0 0 auto;
  }
  .topbar { height: auto; min-height: 68px; padding: 12px 14px; align-items: flex-start; justify-content: flex-start; }
  .top-title { font-size: 18px; line-height: 1.3; }
  .course-line { max-width: calc(100vw - 112px); white-space: normal; line-height: 1.5; }
  .main { padding: 14px; overflow-x: hidden; }
}
/* 新增：移动端抽屉菜单紧凑化，仅影响手机/窄屏抽屉，不影响 PC 侧边栏 */
@media (max-width: 768px) {
  .app-layout {
    min-height: 100dvh;
  }

  .topbar {
    min-height: 58px;
    gap: 10px;
    padding: 10px 12px;
  }

  .top-title {
    font-size: 16px;
  }

  .course-line {
    max-width: calc(100vw - 104px);
    margin-top: 3px;
    font-size: 12px;
    line-height: 1.35;
  }

  .main {
    padding: 12px;
  }

  :global(.mobile-drawer .el-drawer__body) {
    padding: 10px 12px;
  }

  :global(.mobile-drawer .el-drawer__header) {
    padding: 14px 16px 10px;
  }

  :global(.mobile-drawer .el-menu) {
    gap: 2px;
  }

  :global(.mobile-drawer .el-menu-item) {
    height: 40px;
    line-height: 40px;
    margin-bottom: 2px;
    padding-left: 14px !important;
    border-radius: 10px;
    font-size: 14px;
  }

  .mobile-logout {
    height: 40px;
    min-height: 40px;
    margin-top: 10px;
  }
}
</style>
