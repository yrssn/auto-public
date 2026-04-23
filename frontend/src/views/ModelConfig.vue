<template>
  <div>
    <div class="page-card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px">
        <h3 style="margin: 0; font-size: 16px">模型配置列表</h3>
        <el-button type="primary" @click="openDialog(null)">
          <el-icon><Plus /></el-icon>
          新增配置
        </el-button>
      </div>

      <el-table :data="configs" stripe style="width: 100%" v-loading="loading">
        <el-table-column prop="name" label="名称" width="150" />
        <el-table-column prop="provider" label="供应商" width="120" />
        <el-table-column label="类型" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.model_type === 'image' ? 'warning' : row.model_type === 'vision' ? 'success' : 'primary'" size="small">
              {{ row.model_type === 'image' ? '图片生成' : row.model_type === 'vision' ? '视觉' : '聊天' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="model_name" label="模型" width="180" />
        <el-table-column prop="base_url" label="Base URL" min-width="200" show-overflow-tooltip />
        <el-table-column label="API Key" width="140">
          <template #default="{ row }">
            <span>{{ row.api_key.slice(0, 8) }}****</span>
          </template>
        </el-table-column>
        <el-table-column label="默认" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success" size="small">是</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="center">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDialog(row)">编辑</el-button>
            <el-popconfirm title="确认删除？" @confirm="handleDelete(row.id)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Dialog -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑配置' : '新增配置'"
      width="500px"
      destroy-on-close
    >
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="如：GPT-4o 生产环境" />
        </el-form-item>
        <el-form-item label="供应商">
          <el-select v-model="form.provider" placeholder="选择供应商" style="width: 100%">
            <el-option label="OpenAI" value="openai" />
            <el-option label="DeepSeek" value="deepseek" />
            <el-option label="智谱 AI" value="zhipu" />
            <el-option label="通义千问" value="qwen" />
            <el-option label="字节豆包" value="doubao" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型类型">
          <el-radio-group v-model="form.model_type">
            <el-radio value="chat">聊天模型（提示词优化）</el-radio>
            <el-radio value="vision">视觉模型（图片分析）</el-radio>
            <el-radio value="image">图片生成模型</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="form.model_name" placeholder="如：gpt-4o / deepseek-chat" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" placeholder="sk-..." show-password />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="form.base_url" placeholder="留空则使用默认地址" />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="form.is_default" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { modelConfigAPI } from '../api'
import { ElMessage } from 'element-plus'

const configs = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)

const emptyForm = () => ({
  name: '',
  provider: 'openai',
  model_name: '',
  api_key: '',
  base_url: '',
  model_type: 'chat',
  is_default: false,
})
const form = ref(emptyForm())

async function fetchConfigs() {
  loading.value = true
  try {
    const res = await modelConfigAPI.list()
    configs.value = res.data
  } catch (err) {
    ElMessage.error('加载配置失败')
  } finally {
    loading.value = false
  }
}

function openDialog(row) {
  if (row) {
    editingId.value = row.id
    form.value = { ...row }
  } else {
    editingId.value = null
    form.value = emptyForm()
  }
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.value.name || !form.value.model_name || !form.value.api_key) {
    ElMessage.warning('请填写必填项')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await modelConfigAPI.update(editingId.value, form.value)
      ElMessage.success('更新成功')
    } else {
      await modelConfigAPI.create(form.value)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await fetchConfigs()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '操作失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(id) {
  try {
    await modelConfigAPI.delete(id)
    ElMessage.success('已删除')
    await fetchConfigs()
  } catch (err) {
    ElMessage.error('删除失败')
  }
}

onMounted(fetchConfigs)
</script>
