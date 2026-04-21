<template>
  <div>
    <!-- Generate Form -->
    <div class="page-card">
      <h3 style="margin: 0 0 20px; font-size: 16px">生成商品图片</h3>
      <el-form :model="form" label-width="100px">
        <el-form-item label="商品描述">
          <el-input
            v-model="form.prompt"
            type="textarea"
            :rows="4"
            placeholder="描述您想要生成的商品图片，例如：一款简约白色陶瓷咖啡杯，放在木质桌面上，背景是温暖的咖啡馆..."
          />
        </el-form-item>
        <el-form-item label="模型配置">
          <el-select
            v-model="form.model_config_id"
            placeholder="使用默认配置"
            clearable
            style="width: 100%"
          >
            <el-option
              v-for="c in modelConfigs"
              :key="c.id"
              :label="`${c.name} (${c.model_name})`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="优化提示词">
          <el-switch v-model="form.optimize_prompt" />
          <span style="margin-left: 8px; color: #909399; font-size: 13px">
            AI 自动优化为专业的图片生成提示词
          </span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="generating" @click="handleGenerate">
            <el-icon><MagicStick /></el-icon>
            生成图片
          </el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- Task History -->
    <div class="page-card" style="margin-top: 16px">
      <h3 style="margin: 0 0 20px; font-size: 16px">生成记录</h3>
      <el-table :data="tasks" stripe v-loading="loadingTasks" style="width: 100%">
        <el-table-column label="商品描述" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.prompt }}</template>
        </el-table-column>
        <el-table-column label="优化后提示词" min-width="250" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="color: #409eff">{{ row.optimized_prompt || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag
              :type="statusMap[row.status]?.type"
              size="small"
            >
              {{ statusMap[row.status]?.label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="图片" width="120" align="center">
          <template #default="{ row }">
            <el-image
              v-if="row.image_url"
              :src="row.image_url"
              :preview-src-list="[row.image_url]"
              style="width: 60px; height: 60px; border-radius: 4px"
              fit="cover"
            />
            <span v-else style="color: #c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="错误" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error_msg" style="color: #f56c6c">{{ row.error_msg }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString('zh-CN') }}
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { imageGenAPI, modelConfigAPI } from '../api'
import { ElMessage } from 'element-plus'

const form = ref({
  prompt: '',
  model_config_id: null,
  optimize_prompt: true,
})

const generating = ref(false)
const tasks = ref([])
const loadingTasks = ref(false)
const modelConfigs = ref([])

const statusMap = {
  pending: { label: '等待中', type: 'info' },
  generating: { label: '生成中', type: 'warning' },
  done: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

async function fetchTasks() {
  loadingTasks.value = true
  try {
    const res = await imageGenAPI.list()
    tasks.value = res.data
  } finally {
    loadingTasks.value = false
  }
}

async function fetchModelConfigs() {
  try {
    const res = await modelConfigAPI.list()
    modelConfigs.value = res.data
  } catch {}
}

async function handleGenerate() {
  if (!form.value.prompt.trim()) {
    ElMessage.warning('请输入商品描述')
    return
  }
  generating.value = true
  try {
    await imageGenAPI.generate(form.value)
    ElMessage.success('生成任务已提交')
    form.value.prompt = ''
    await fetchTasks()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '生成失败')
  } finally {
    generating.value = false
  }
}

onMounted(() => {
  fetchTasks()
  fetchModelConfigs()
})
</script>
