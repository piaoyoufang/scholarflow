<template>
  <div>
    <h1 class="page-title">自动出题</h1><p class="page-desc">围绕指定主题自动生成选择题、判断题、简答题或面试题。</p>
    <div v-if="!auth.hasCourse" class="empty-state">请先选择课程。</div>
    <el-card v-else class="panel-card"><el-form :model="form" label-position="top"><el-form-item label="出题主题"><el-input v-model="form.topic" placeholder="例如：RAG 检索增强生成" /></el-form-item><div class="grid grid-3"><el-form-item label="题目数量"><el-input-number v-model="form.question_count" :min="1" :max="20" /></el-form-item><el-form-item label="题型"><el-select v-model="form.question_type"><el-option label="single_choice" value="single_choice"/><el-option label="true_false" value="true_false"/><el-option label="short_answer" value="short_answer"/><el-option label="interview" value="interview"/></el-select></el-form-item><el-form-item label="难度"><el-select v-model="form.difficulty"><el-option label="easy" value="easy"/><el-option label="medium" value="medium"/><el-option label="hard" value="hard"/></el-select></el-form-item></div><el-button type="primary" :loading="loading" @click="generate">生成题目</el-button></el-form></el-card>
    <el-collapse v-if="items.length"><el-collapse-item v-for="(it,i) in items" :key="i" :title="`第 ${i+1} 题：${it.question || ''}`"><ul><li v-for="(op,j) in it.options || []" :key="j">{{ op }}</li></ul><p><b>参考答案：</b>{{ it.answer }}</p><p><b>解析：</b>{{ it.explanation }}</p></el-collapse-item></el-collapse>
  </div>
</template>
<script setup>
import { reactive, ref } from 'vue'; import { ElMessage } from 'element-plus'; import { courseApi } from '../api'; import { errorMessage } from '../api/request'; import { useAuthStore } from '../stores/auth'
const auth=useAuthStore(); const loading=ref(false); const items=ref([]); const form=reactive({topic:'',question_count:5,question_type:'single_choice',difficulty:'easy'})
async function generate(){ if(!form.topic.trim()) return ElMessage.error('出题主题不能为空'); loading.value=true; try{ const {data}=await courseApi.quiz(auth.currentCourseId,{...form,topic:form.topic.trim()}); items.value=data.items||[]; ElMessage.success('题目生成成功') }catch(e){ ElMessage.error(errorMessage(e)) }finally{ loading.value=false } }
</script>
