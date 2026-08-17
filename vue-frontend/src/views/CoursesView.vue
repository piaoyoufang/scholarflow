<template>
  <div class="courses-page">
    <el-breadcrumb separator="/" class="breadcrumb">
      <el-breadcrumb-item>高校课程AI学习助手平台</el-breadcrumb-item>
      <el-breadcrumb-item>我的课程</el-breadcrumb-item>
    </el-breadcrumb>

    <h1 class="page-title">我的课程</h1>
    <p class="page-desc">{{ auth.isTeacher ? '创建或选择当前课程，后续知识库、问答、出题和分析都会围绕这门课工作。' : '选择你已加入的课程，后续 AI 问答、学习计划和自动出题都会围绕这门课工作。' }}</p>

    <el-card v-if="auth.isTeacher" class="panel-card create-card">
      <template #header>
        <div class="card-header">
          <span>创建课程</span>
          <el-tag type="info" effect="plain">教师工作台</el-tag>
        </div>
      </template>
      <el-form ref="courseFormRef" :model="form" :rules="rules" label-position="top" class="course-form">
        <el-form-item label="课程名称" prop="course_name">
          <el-input v-model="form.course_name" placeholder="例如：AI应用开发实战课" clearable />
        </el-form-item>
        <el-form-item label="课程说明" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="4" placeholder="这门课包含 RAG、Agent、评估、部署等资料。" />
        </el-form-item>
        <el-button type="primary" :loading="creating" :disabled="creating" @click="createCourse">创建课程</el-button>
      </el-form>
    </el-card>

    <div class="toolbar">
      <h2>选择当前课程</h2>
      <el-button :loading="loading" @click="loadCourses">刷新课程</el-button>
    </div>

    <el-empty v-if="!courses.length" class="course-empty" :description="auth.isTeacher ? '你还没有课程，可以先在上方创建课程。' : '你还没有加入任何课程，请联系任课老师添加你为课程成员。'" />

    <div v-else class="grid grid-3 course-grid">
      <el-card v-for="course in courses" :key="course.course_id" class="course-card" :class="{ active: course.course_id === auth.currentCourseId }" @click="selectCourse(course)">
        <div class="course-top">
          <h3>{{ course.course_name || '未命名课程' }}</h3>
          <el-tag :type="course.role_in_course === 'teacher' ? 'primary' : 'success'" effect="light" round>{{ roleLabel(course.role_in_course) }}</el-tag>
        </div>
        <p>{{ course.description || '暂无课程说明' }}</p>
      </el-card>
    </div>

    <el-card class="panel-card table-card" v-if="courses.length">
      <template #header><div class="card-header"><span>课程明细</span><el-tag effect="plain">{{ courses.length }} 门课程</el-tag></div></template>
      <el-table :data="courses" stripe style="width:100%">
        <el-table-column prop="course_name" label="课程名称" min-width="180" />
        <el-table-column prop="description" label="课程说明" min-width="260" show-overflow-tooltip />
        <el-table-column prop="role_in_course" label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="row.role_in_course === 'teacher' ? 'primary' : 'success'" effect="light" round>
              {{ roleLabel(row.role_in_course) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { courseApi } from '../api'
import { errorMessage } from '../api/request'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const courses = ref([])
const creating = ref(false)
const loading = ref(false)
const courseFormRef = ref()
const form = reactive({ course_name: '', description: '' })
const rules = {
  course_name: [
    { required: true, message: '请输入课程名称', trigger: 'blur' },
    { min: 2, max: 40, message: '课程名称长度建议为 2-40 个字符', trigger: 'blur' }
  ],
  description: [
    { max: 300, message: '课程说明最多 300 个字符', trigger: 'blur' }
  ]
}

async function loadCourses() {
  loading.value = true
  try {
    const { data } = await courseApi.list()
    courses.value = data.courses || []
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    loading.value = false
  }
}

async function createCourse() {
  await courseFormRef.value?.validate()
  creating.value = true
  try {
    const { data } = await courseApi.create({ course_name: form.course_name.trim(), description: form.description.trim() })
    const c = data.course || {}
    auth.setCourse({ ...c, role_in_course: 'teacher' })
    ElMessage.success('课程创建成功')
    form.course_name = ''
    form.description = ''
    courseFormRef.value?.clearValidate()
    await loadCourses()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    creating.value = false
  }
}

function selectCourse(course) {
  auth.setCourse(course)
  ElMessage.success(`当前课程：${course.course_name}`)
}

function roleLabel(role) {
  const map = { teacher: '教师', student: '学生', assistant: '助教', admin: '管理员' }
  return map[role] || '未知'
}

onMounted(loadCourses)
</script>

<style scoped>
.courses-page { max-width: 1180px; margin: 0 auto; }
.breadcrumb { margin-bottom: 18px; }
.breadcrumb :deep(.el-breadcrumb__inner) { color: #cbd5e1; font-weight: 700; }
.create-card { margin-bottom: 24px; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-weight: 900; color: #0f172a; }
.course-form { display: grid; gap: 4px; }
.toolbar { color:#fff; }
.toolbar h2 { margin: 0; font-size: 20px; font-weight: 900; }
.course-empty { padding: 46px 0; border: 1px dashed rgba(147,197,253,.55); border-radius: 22px; background: rgba(239,246,255,.08); }
.course-empty :deep(.el-empty__description p) { color: #cbd5e1; }
.course-grid { margin-top: 8px; }
.course-card { cursor:pointer; min-height: 196px; border: 1px solid rgba(226,232,240,.72); transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease; position: relative; overflow: hidden; }
.course-card::before { content: ''; position: absolute; inset: 0 0 auto 0; height: 4px; background: transparent; transition: .2s ease; }
.course-card:hover { transform: translateY(-4px); border-color:#60a5fa; box-shadow:0 18px 42px rgba(59,130,246,.24); }
.course-card.active { border-color:#3b82f6; box-shadow:0 20px 48px rgba(59,130,246,.30); }
.course-card.active::before { background: linear-gradient(90deg,#2563eb,#06b6d4); }
.course-top { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.course-card h3 { margin:0 0 10px; color:#0f172a; font-size: 18px; font-weight: 900; }
.course-card p { color:#64748b; line-height:1.75; min-height:52px; margin: 0; }
.table-card { margin-top: 22px; }
</style>
