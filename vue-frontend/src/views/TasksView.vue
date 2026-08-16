<template><div><h1 class="page-title">上传任务</h1><p class="page-desc">查看课程资料入库任务状态，快速定位解析或向量化进度。</p><div v-if="!auth.hasCourse" class="empty-state">请先选择课程。</div><template v-else><el-card class="panel-card"><div class="toolbar"><h2>当前课程最近任务</h2><el-button @click="loadTasks">刷新</el-button></div><div v-if="!tasks.length" class="empty-state">当前课程还没有上传任务。</div><el-table v-else :data="tasks" stripe style="width:100%"/></el-card><el-card class="panel-card"><h2>按任务ID查询</h2><el-input v-model="taskId" placeholder="粘贴上传接口返回的 task_id"/><el-button type="primary" @click="queryTask">查询任务状态</el-button><pre v-if="task">{{ task }}</pre></el-card></template></div></template>
<script setup>
import { onMounted, ref } from 'vue'; import { ElMessage } from 'element-plus'; import { courseApi, taskApi } from '../api'; import { errorMessage } from '../api/request'; import { useAuthStore } from '../stores/auth'
const auth=useAuthStore(); const tasks=ref([]); const taskId=ref(auth.lastTaskId||''); const task=ref(null)
async function loadTasks(){ if(!auth.currentCourseId)return; try{ const {data}=await courseApi.tasks(auth.currentCourseId); tasks.value=data.tasks||[] }catch(e){ ElMessage.error(errorMessage(e)) } }
async function queryTask(){ if(!taskId.value.trim()) return ElMessage.error('请先输入 task_id'); auth.lastTaskId=taskId.value.trim(); auth.persist(); try{ const {data}=await taskApi.detail(taskId.value.trim()); task.value=data.task||data }catch(e){ ElMessage.error(errorMessage(e)) } }
onMounted(loadTasks)
</script>
<style scoped>.panel-card{margin-bottom:18px}.el-input{margin:10px 0 12px}pre{white-space:pre-wrap;color:#0f172a;background:#f8fafc;padding:14px;border-radius:12px}</style>
