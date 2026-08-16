import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import LoginView from '../views/LoginView.vue'
import DashboardLayout from '../layouts/DashboardLayout.vue'
import CoursesView from '../views/CoursesView.vue'
import DocumentsView from '../views/DocumentsView.vue'
import ChatView from '../views/ChatView.vue'
import LearningPlanView from '../views/LearningPlanView.vue'
import QuizView from '../views/QuizView.vue'
import RetrievalDebugView from '../views/RetrievalDebugView.vue'
import AnalyticsView from '../views/AnalyticsView.vue'
import DashboardView from '../views/DashboardView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    {
      path: '/',
      component: DashboardLayout,
      redirect: '/courses',
      meta: { requiresAuth: true },
      children: [
        { path: 'courses', name: 'courses', component: CoursesView, meta: { title: '我的课程' } },
        { path: 'documents', name: 'documents', component: DocumentsView, meta: { title: '课程知识库' } },
        { path: 'chat', name: 'chat', component: ChatView, meta: { title: 'AI 问答' } },
        { path: 'learning-plan', name: 'learning-plan', component: LearningPlanView, meta: { title: '学习计划' } },
        { path: 'quiz', name: 'quiz', component: QuizView, meta: { title: '自动出题' } },
        { path: 'retrieval-debug', name: 'retrieval-debug', component: RetrievalDebugView, meta: { title: '检索可视化' } },
        { path: 'tasks', redirect: '/documents' },
        { path: 'analytics', name: 'analytics', component: AnalyticsView, meta: { title: '问答分析' } },
        { path: 'dashboard', name: 'dashboard', component: DashboardView, meta: { title: '课程看板' } }
      ]
    }
  ]
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  auth.restoreFromStorage()
  if (to.meta.requiresAuth && !auth.accessToken) return '/login'
  if (to.path === '/login' && auth.accessToken) return '/courses'
  return true
})

export default router
