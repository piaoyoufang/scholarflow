<template>
  <div>
    <h1 class="page-title">课程知识库</h1><p class="page-desc">上传课程资料，后台异步解析、切块并写入向量库。</p>
    <div v-if="!auth.hasCourse" class="empty-state">请先在“我的课程”里创建或选择一门课程。</div>
    <template v-else>
      <el-card class="panel-card">
        <el-upload drag :auto-upload="false" :limit="1" :on-change="onFileChange" :on-remove="onRemove" accept=".pdf,.txt,.md">
          <div class="upload-text">拖拽 PDF / TXT / Markdown 到这里，或点击选择文件</div>
        </el-upload>
        <el-button type="primary" :disabled="!file" :loading="uploading" @click="upload">上传并创建入库任务</el-button>
      </el-card>
      <div class="toolbar"><h2>当前课程文档列表</h2><el-button @click="loadDocuments">刷新</el-button></div>
      <div v-if="!documents.length" class="empty-state">这门课程暂时没有入库文档。请先上传课程资料。</div>
      <div v-else class="grid grid-2">
        <el-card v-for="doc in documents" :key="doc.source_id" class="doc-card">
          <h3>{{ doc.original_name }}</h3>
          <p>状态：{{ doc.status }} ｜ 类型：{{ doc.file_type || '未知' }} ｜ 切片：{{ doc.chunk_count || 0 }}</p>
          <p class="id">{{ doc.source_id }}</p>
          <div class="actions"><el-button @click="reingest(doc)">重新入库</el-button><el-button type="danger" plain @click="remove(doc)">删除资料</el-button></div>
        </el-card>
      </div>
      <el-card v-if="documents.length" class="panel-card table-card"><el-table :data="documents" stripe style="width:100%" /></el-card>
    </template>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { courseApi } from '../api'
import { errorMessage } from '../api/request'
import { useAuthStore } from '../stores/auth'
const auth = useAuthStore(); const documents = ref([]); const file = ref(null); const uploading = ref(false)
function onFileChange(uploadFile) { file.value = uploadFile.raw }
function onRemove() { file.value = null }
async function loadDocuments(){ if(!auth.currentCourseId) return; try{ const {data}=await courseApi.documents(auth.currentCourseId); documents.value=data.documents||[] }catch(e){ ElMessage.error(errorMessage(e)) } }
async function upload(){ uploading.value=true; try{ const {data}=await courseApi.uploadDocument(auth.currentCourseId,file.value); auth.lastTaskId=data.task_id||''; auth.persist(); ElMessage.success(`上传成功，任务ID：${auth.lastTaskId}`); await loadDocuments() }catch(e){ ElMessage.error(errorMessage(e)) }finally{ uploading.value=false } }
async function reingest(doc){ try{ const {data}=await courseApi.reingestDocument(auth.currentCourseId,doc.source_id); auth.lastTaskId=data.task_id||''; auth.persist(); ElMessage.success(`已创建重新入库任务：${auth.lastTaskId}`) }catch(e){ ElMessage.error(errorMessage(e)) } }
async function remove(doc){ await ElMessageBox.confirm('确认删除该资料？','删除资料'); try{ await courseApi.deleteDocument(auth.currentCourseId,doc.source_id); ElMessage.success('资料已删除'); await loadDocuments() }catch(e){ ElMessage.error(errorMessage(e)) } }
onMounted(loadDocuments)
</script>
<style scoped>.panel-card{margin-bottom:20px}.upload-text{color:#475569}.toolbar{color:#fff}.toolbar h2{margin:0}.doc-card h3{margin:0 0 10px;color:#0f172a}.doc-card p{color:#64748b}.id{font-size:12px;word-break:break-all}.actions{display:flex;gap:10px;margin-top:14px}.table-card{margin-top:18px}</style>
