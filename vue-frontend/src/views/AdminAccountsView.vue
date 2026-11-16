<template>
  <div class="admin-page">
    <el-breadcrumb separator="/" class="breadcrumb">
      <el-breadcrumb-item>高校课程AI学习助手平台</el-breadcrumb-item>
      <el-breadcrumb-item>账号管理</el-breadcrumb-item>
    </el-breadcrumb>

    <h1 class="page-title">账号管理</h1>
    <p class="page-desc">管理员统一管理平台账号：创建账号、调整教师/学生身份、重置密码、禁用账号、强制下线与删除账号。</p>

    <el-card class="panel-card create-card">
      <template #header>
        <div class="card-header">
          <span>创建账号</span>
          <el-tag type="warning" effect="plain">免邀请码</el-tag>
        </div>
      </template>
      <el-form ref="createFormRef" :model="form" :rules="rules" label-position="top">
        <el-row :gutter="16">
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="用户名" prop="username">
              <el-input v-model="form.username" maxlength="32" placeholder="字母、数字或下划线" clearable autocomplete="off" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="初始密码" prop="password">
              <el-input v-model="form.password" type="password" show-password maxlength="128" placeholder="至少 8 位" autocomplete="new-password" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="身份" prop="role">
              <el-select v-model="form.role" style="width: 100%">
                <el-option label="教师" value="teacher" />
                <el-option label="学生" value="student" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <div class="form-actions">
          <el-button type="primary" :loading="creating" :disabled="creating" @click="createUser">创建账号</el-button>
        </div>
      </el-form>
    </el-card>

    <div class="toolbar">
      <h2>账号列表</h2>
      <div class="toolbar-actions">
        <el-input v-model="keyword" placeholder="搜索用户名" clearable style="width: 220px" />
        <el-button :loading="loading" @click="loadUsers">刷新列表</el-button>
      </div>
    </div>

    <el-empty v-if="!loading && !filteredUsers.length" description="暂无账号" />

    <el-card v-else class="panel-card table-card">
      <el-table :data="filteredUsers" stripe style="width:100%">
        <el-table-column label="用户名" min-width="150">
          <template #default="{ row }">
            <div class="user-cell">
              <span>{{ row.username }}</span>
              <el-tag v-if="row.is_admin" type="warning" effect="dark" round size="small">管理员</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="身份" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'teacher' ? 'primary' : 'success'" effect="light" round>
              {{ row.role === 'teacher' ? '教师' : '学生' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.disabled ? 'danger' : 'success'" effect="plain" round>
              {{ row.disabled ? '已禁用' : '正常' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="course_count" label="课程数" width="90" />
        <el-table-column prop="active_sessions" label="在线会话" width="100" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="430" fixed="right">
          <template #default="{ row }">
            <div class="row-actions">
              <el-button size="small" plain :disabled="row.is_admin" @click="toggleRole(row)">
                {{ row.role === 'teacher' ? '转为学生' : '转为教师' }}
              </el-button>
              <el-button size="small" plain type="warning" :disabled="row.is_admin" @click="resetPassword(row)">重置密码</el-button>
              <el-button size="small" plain :type="row.disabled ? 'success' : 'danger'" :disabled="row.is_admin" @click="toggleDisabled(row)">
                {{ row.disabled ? '启用' : '禁用' }}
              </el-button>
              <el-button size="small" plain :disabled="row.is_admin || !row.active_sessions" @click="revokeSessions(row)">强制下线</el-button>
              <el-button size="small" type="danger" plain :disabled="row.is_admin" @click="removeUser(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi } from '../api'
import { errorMessage } from '../api/request'

const users = ref([])
const keyword = ref('')
const loading = ref(false)
const creating = ref(false)
const createFormRef = ref()
const form = reactive({ username: '', password: '', role: 'student' })
const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_]{3,32}$/, message: '用户名为 3-32 位字母、数字或下划线', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入初始密码', trigger: 'blur' },
    { min: 8, max: 128, message: '密码长度需为 8-128 位', trigger: 'blur' }
  ],
  role: [{ required: true, message: '请选择身份', trigger: 'change' }]
}

const filteredUsers = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return users.value
  return users.value.filter((user) => user.username.toLowerCase().includes(key))
})

function formatTime(value) {
  if (!value) return '-'
  let text = String(value)
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text)) {
    text = text.replace(' ', 'T') + 'Z'
  }
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? text : date.toLocaleString('zh-CN', { hour12: false })
}

async function loadUsers() {
  loading.value = true
  try {
    const { data } = await adminApi.listUsers()
    users.value = data.users || []
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    loading.value = false
  }
}

async function createUser() {
  await createFormRef.value?.validate()
  creating.value = true
  try {
    await adminApi.createUser({
      username: form.username.trim(),
      password: form.password,
      role: form.role
    })
    ElMessage.success('账号创建成功')
    form.username = ''
    form.password = ''
    form.role = 'student'
    createFormRef.value?.clearValidate()
    await loadUsers()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    creating.value = false
  }
}

async function toggleRole(row) {
  const nextRole = row.role === 'teacher' ? 'student' : 'teacher'
  const label = nextRole === 'teacher' ? '教师' : '学生'
  try {
    await ElMessageBox.confirm(`确定将「${row.username}」的身份改为${label}吗？`, '修改身份', {
      type: 'warning',
      confirmButtonText: '确定修改',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  try {
    await adminApi.updateUserRole(row.user_id, { role: nextRole })
    ElMessage.success(`已改为${label}身份`)
    await loadUsers()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function resetPassword(row) {
  let value
  try {
    const result = await ElMessageBox.prompt('请输入新密码（8-128 位），重置后该账号所有会话会立即下线。', '重置密码', {
      inputType: 'password',
      inputPattern: /^.{8,128}$/,
      inputErrorMessage: '密码长度需为 8-128 位',
      confirmButtonText: '确认重置',
      cancelButtonText: '取消'
    })
    value = result.value
  } catch {
    return
  }
  try {
    await adminApi.resetPassword(row.user_id, { new_password: value })
    ElMessage.success('密码已重置')
    await loadUsers()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function toggleDisabled(row) {
  const nextDisabled = !row.disabled
  try {
    await ElMessageBox.confirm(
      nextDisabled ? `禁用后「${row.username}」将无法登录，且当前会话立即失效。确定禁用吗？` : `确定重新启用「${row.username}」吗？`,
      nextDisabled ? '禁用账号' : '启用账号',
      { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await adminApi.setUserDisabled(row.user_id, { disabled: nextDisabled })
    ElMessage.success(nextDisabled ? '账号已禁用' : '账号已启用')
    await loadUsers()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function revokeSessions(row) {
  try {
    await ElMessageBox.confirm(`确定强制「${row.username}」下线吗？该账号需要重新登录。`, '强制下线', {
      type: 'warning',
      confirmButtonText: '确定下线',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  try {
    const { data } = await adminApi.revokeUserSessions(row.user_id)
    ElMessage.success(`已作废 ${data.revoked ?? 0} 个会话`)
    await loadUsers()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function removeUser(row) {
  try {
    await ElMessageBox.confirm(
      `删除后「${row.username}」的账号、会话与学习记录将无法恢复。确定删除吗？`,
      '删除账号',
      { type: 'error', confirmButtonText: '确定删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  try {
    await adminApi.deleteUser(row.user_id)
    ElMessage.success('账号已删除')
    await loadUsers()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

onMounted(loadUsers)
</script>

<style scoped>
.admin-page { max-width: 1180px; margin: 0 auto; }
.breadcrumb { margin-bottom: 18px; }
.breadcrumb :deep(.el-breadcrumb__inner) { color: rgba(255,255,255,.5); font-weight: 500; font-size: 12px; }
.create-card { margin-bottom: 24px; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-weight: 600; color: #fff; font-size: 14px; }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #fff; flex-wrap: wrap; }
.toolbar h2 { margin: 0; font-size: 20px; font-weight: 900; }
.toolbar-actions { display: flex; align-items: center; gap: 10px; }
.user-cell { display: flex; align-items: center; gap: 8px; }
.form-actions { display: flex; justify-content: flex-end; margin-top: 2px; }
.form-actions :deep(.el-button) { min-width: 120px; }
.row-actions { display: flex; flex-wrap: nowrap; gap: 6px; }
.row-actions :deep(.el-button) { margin-left: 0; white-space: nowrap; }
.table-card { margin-top: 14px; }
@media (max-width: 768px) {
  .admin-page { max-width: 100%; margin: 0; }
  .create-card { margin-bottom: 16px; }
  .toolbar { align-items: flex-start; }
  .toolbar-actions { width: 100%; }
  .toolbar-actions :deep(.el-input) { flex: 1; width: auto !important; }
  .toolbar h2 { font-size: 18px; }
}
</style>
