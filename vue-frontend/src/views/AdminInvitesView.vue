<template>
  <div class="admin-page">
    <el-breadcrumb separator="/" class="breadcrumb">
      <el-breadcrumb-item>高校课程AI学习助手平台</el-breadcrumb-item>
      <el-breadcrumb-item>教师邀请码</el-breadcrumb-item>
    </el-breadcrumb>

    <h1 class="page-title">教师邀请码</h1>
    <p class="page-desc">教师注册必须使用一次性邀请码。邀请码明文只在生成时显示一次，数据库仅保存哈希；未使用的码可随时重新签发，也可设置有效期并吊销。</p>

    <el-card class="panel-card create-card">
      <template #header>
        <div class="card-header">
          <span>生成邀请码</span>
          <el-tag type="warning" effect="plain">一次性随机码</el-tag>
        </div>
      </template>
      <el-form ref="createFormRef" :model="form" :rules="rules" label-position="top">
        <el-row :gutter="16">
          <el-col :xs="24" :sm="12" :md="8">
            <el-form-item label="有效期（天）" prop="expires_in_days">
              <el-input-number v-model="form.expires_in_days" :min="1" :max="90" :step="1" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12" :md="16">
            <el-form-item label="备注（可选）" prop="note">
              <el-input v-model="form.note" maxlength="120" placeholder="例如：给新入职的张老师" clearable autocomplete="off" />
            </el-form-item>
          </el-col>
        </el-row>
        <div class="form-actions">
          <el-button type="primary" :loading="creating" :disabled="creating" @click="createInvite">生成邀请码</el-button>
        </div>
      </el-form>

      <div v-if="created" class="created-code">
        <div class="created-head">
          <span>{{ created.reissued ? '邀请码已重新签发' : '邀请码已生成' }}，请立即复制并转交使用者（仅显示这一次）</span>
          <el-button size="small" text @click="created = null">关闭</el-button>
        </div>
        <div class="created-row">
          <strong>{{ created.code }}</strong>
          <div class="created-actions">
            <el-button size="small" type="primary" plain @click="copyCode(created.code)">复制</el-button>
            <el-button size="small" plain @click="downloadCode">下载</el-button>
          </div>
        </div>
        <div class="created-foot">有效期至：{{ formatTime(created.expires_at) }}</div>
      </div>
    </el-card>

    <div class="toolbar">
      <h2>邀请码记录</h2>
      <el-button :loading="loading" @click="loadInvites">刷新列表</el-button>
    </div>

    <el-empty v-if="!loading && !invites.length" description="还没有生成过邀请码" />

    <el-card v-else class="panel-card table-card">
      <div class="table-scroll">
        <el-table :data="invites" stripe style="width:100%">
          <el-table-column prop="note" label="备注" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.note || '-' }}</template>
          </el-table-column>
          <el-table-column label="码指纹" width="104">
            <template #default="{ row }">
              <span class="fingerprint" :title="'哈希指纹，无法还原明文邀请码'">{{ row.code_fingerprint ? row.code_fingerprint + '…' : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="96">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" effect="light" round>{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建人" width="116">
            <template #default="{ row }">{{ row.created_by }}</template>
          </el-table-column>
          <el-table-column label="创建时间" width="168">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="过期时间" width="168">
            <template #default="{ row }">{{ formatTime(row.expires_at) }}</template>
          </el-table-column>
          <el-table-column label="使用情况" min-width="168">
            <template #default="{ row }">
              <span v-if="row.used_at">{{ formatTime(row.used_at) }}<template v-if="row.used_by_name"> ／ {{ row.used_by_name }}</template></span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <div class="row-actions">
                <el-button
                  v-if="row.status === 'unused' || row.status === 'expired'"
                  size="small"
                  type="primary"
                  plain
                  @click="reissueInvite(row)"
                >重新签发</el-button>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :disabled="row.status !== 'unused'"
                  @click="revokeInvite(row)"
                >吊销</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi } from '../api'
import { errorMessage } from '../api/request'

const invites = ref([])
const created = ref(null)
const loading = ref(false)
const creating = ref(false)
const createFormRef = ref()
const form = reactive({ expires_in_days: 7, note: '' })
const rules = {
  expires_in_days: [{ required: true, message: '请选择有效期', trigger: 'change' }]
}

const STATUS = {
  unused: { label: '未使用', type: 'success' },
  used: { label: '已使用', type: 'info' },
  expired: { label: '已过期', type: 'warning' },
  revoked: { label: '已吊销', type: 'danger' }
}

function statusLabel(status) {
  return STATUS[status]?.label || status
}

function statusType(status) {
  return STATUS[status]?.type || 'info'
}

function formatTime(value) {
  if (!value) return '-'
  let text = String(value)
  // SQLite CURRENT_TIMESTAMP 为 UTC 且无时区标记，补上 Z 避免前端按本地时间解析
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text)) {
    text = text.replace(' ', 'T') + 'Z'
  }
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? text : date.toLocaleString('zh-CN', { hour12: false })
}

async function loadInvites() {
  loading.value = true
  try {
    const { data } = await adminApi.listInvites()
    invites.value = data || []
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    loading.value = false
  }
}

async function createInvite() {
  await createFormRef.value?.validate()
  creating.value = true
  try {
    const { data } = await adminApi.createInvite({
      expires_in_days: form.expires_in_days,
      note: form.note.trim()
    })
    created.value = data
    form.note = ''
    ElMessage.success('邀请码生成成功')
    await loadInvites()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  } finally {
    creating.value = false
  }
}

async function reissueInvite(row) {
  let days
  try {
    const { value } = await ElMessageBox.prompt(
      '重新签发后旧邀请码立即失效，备注与记录保留。请输入新的有效天数：',
      '重新签发邀请码',
      {
        confirmButtonText: '重新签发',
        cancelButtonText: '取消',
        inputValue: String(form.expires_in_days),
        inputPattern: /^([1-9]|[1-8][0-9]|90)$/,
        inputErrorMessage: '请输入 1 到 90 之间的整数'
      }
    )
    days = Number(value)
  } catch {
    return
  }
  try {
    const { data } = await adminApi.reissueInvite(row.invite_id, {
      expires_in_days: days,
      note: row.note || ''
    })
    created.value = { ...data, reissued: true }
    ElMessage.success('邀请码已重新签发')
    await loadInvites()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

function downloadCode() {
  const item = created.value
  if (!item) return
  const text = [
    '高校课程AI学习助手平台 · 教师邀请码',
    `邀请码：${item.code}`,
    `有效期至：${formatTime(item.expires_at)}`,
    item.note ? `备注：${item.note}` : '',
    '',
    '教师注册时填写该邀请码即可获得教师身份，该码仅可使用一次。'
  ].filter((line) => line !== '').join('\n')
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `教师邀请码-${item.code}.txt`
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('邀请码文件已下载')
}

async function revokeInvite(row) {
  try {
    await ElMessageBox.confirm('吊销后该邀请码将立即失效，且无法恢复。确定吊销吗？', '吊销邀请码', {
      type: 'warning',
      confirmButtonText: '确定吊销',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  try {
    await adminApi.revokeInvite(row.invite_id)
    ElMessage.success('邀请码已吊销')
    await loadInvites()
  } catch (e) {
    ElMessage.error(errorMessage(e))
  }
}

async function copyCode(code) {
  try {
    await navigator.clipboard.writeText(code)
    ElMessage.success('邀请码已复制')
  } catch {
    ElMessage.info(`邀请码：${code}`)
  }
}

// 未关闭明文邀请码时，刷新/关闭页面给出浏览器原生确认
function handleBeforeUnload(event) {
  if (!created.value) return
  event.preventDefault()
  event.returnValue = ''
}

// 路由离开前同样提醒：明文码只显示这一次
onBeforeRouteLeave(() => {
  if (!created.value) return true
  return window.confirm('邀请码明文只显示这一次，离开后无法再次查看。确定离开吗？')
})

onMounted(() => {
  loadInvites()
  window.addEventListener('beforeunload', handleBeforeUnload)
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', handleBeforeUnload))
</script>

<style scoped>
.admin-page { max-width: 1180px; margin: 0 auto; }
.breadcrumb { margin-bottom: 18px; }
.breadcrumb :deep(.el-breadcrumb__inner) { color: var(--muted); font-weight: 500; font-size: 12px; }
.create-card { margin-bottom: 24px; }
.card-header { display: flex; align-items: center; justify-content: space-between; font-weight: 600; color: var(--text); font-size: 14px; }
.form-actions { display: flex; justify-content: flex-end; margin-top: 2px; }
.form-actions :deep(.el-button) { min-width: 120px; }
.created-code { margin-top: 6px; padding: 16px; border-radius: 14px; border: 1px solid rgba(124,58,237,.24); background: rgba(124,58,237,.06); }
.created-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #6d28d9; font-size: 13px; font-weight: 600; }
.created-row { display: flex; align-items: center; gap: 12px; margin: 12px 0 8px; }
.created-actions { display: flex; gap: 8px; }
.fingerprint { font-family: "JetBrains Mono", Consolas, monospace; font-size: 12px; letter-spacing: .04em; color: var(--muted); }
.created-row strong { color: var(--text); font-size: 20px; letter-spacing: .1em; word-break: break-all; }
.created-foot { color: var(--muted); font-size: 12px; }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--text); }
.toolbar h2 { margin: 0; font-size: 20px; font-weight: 900; }
.table-card { margin-top: 14px; }
/* 宽表在窄屏下横向滚动，避免列被压缩挤在一起 */
.table-scroll { width: 100%; overflow-x: auto; }
.table-scroll :deep(.el-table) { min-width: 1160px; }
.row-actions { display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.row-actions :deep(.el-button) { margin-left: 0; }
@media (max-width: 768px) {
  .admin-page { max-width: 100%; margin: 0; }
  .create-card { margin-bottom: 16px; }
  .created-row { flex-direction: column; align-items: flex-start; gap: 8px; }
  .created-actions { width: 100%; }
  .created-row :deep(.el-button) { width: 100%; }
  .toolbar h2 { font-size: 18px; }
}
</style>
