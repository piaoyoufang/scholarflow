<template>
  <div>
    <h1 class="page-title">学习计划</h1><p class="page-desc">输入学习目标，由 Agent 按天拆解任务、产出和难度节奏。</p>
    <div v-if="!auth.hasCourse" class="empty-state">请先选择课程。</div>
    <el-card v-else class="panel-card">
      <el-form :model="form" label-position="top">
        <el-form-item label="学习目标"><el-input v-model="form.goal" type="textarea" :rows="3" placeholder="例如：7天内掌握本课程的 RAG 项目开发流程" /></el-form-item>
        <div class="grid grid-3"><el-form-item label="计划天数"><el-input-number v-model="form.days" :min="1" :max="30" /></el-form-item><el-form-item label="每天学习分钟数"><el-input-number v-model="form.daily_minutes" :min="10" :max="600" /></el-form-item><el-form-item label="难度"><el-select v-model="form.difficulty"><el-option label="beginner" value="beginner"/><el-option label="intermediate" value="intermediate"/><el-option label="advanced" value="advanced"/></el-select></el-form-item></div>
        <el-button type="primary" :loading="loading" @click="generate">生成学习计划</el-button>
      </el-form>
    </el-card>
    <el-collapse v-if="days.length" model-value="1"><el-collapse-item v-for="d in days" :key="d.day" :name="String(d.day)" :title="`第 ${d.day} 天：${d.topic || ''}`"><ul><li v-for="(t,i) in d.tasks || []" :key="i">{{ t }}</li></ul><b v-if="d.expected_output">预期产出：{{ d.expected_output }}</b></el-collapse-item></el-collapse>
  </div>
</template>
<script setup>
import { reactive, ref } from 'vue'; import { ElMessage } from 'element-plus'; import { courseApi } from '../api'; import { errorMessage } from '../api/request'; import { useAuthStore } from '../stores/auth'
const auth=useAuthStore(); const loading=ref(false); const days=ref([]); const form=reactive({goal:'',days:7,daily_minutes:60,difficulty:'beginner'})
async function generate(){ if(!form.goal.trim()) return ElMessage.error('学习目标不能为空'); loading.value=true; try{ const {data}=await courseApi.learningPlan(auth.currentCourseId,{...form,goal:form.goal.trim()}); days.value=data.days||[]; ElMessage.success('学习计划生成成功') }catch(e){ ElMessage.error(errorMessage(e)) }finally{ loading.value=false } }
</script>
