<template>
  <div class="chat-layout">
    <!-- Left: Conversation List -->
    <div class="conv-sidebar">
      <div class="conv-sidebar-header">
        <el-button type="primary" size="small" style="width: 100%" @click="handleNewConv">
          <el-icon><Plus /></el-icon> 新建会话
        </el-button>
      </div>
      <div class="conv-list">
        <div
          v-for="c in conversations"
          :key="c.id"
          class="conv-item"
          :class="{ active: activeConvId === c.id }"
          @click="selectConv(c.id)"
        >
          <span class="conv-title">{{ c.title }}</span>
          <el-icon class="conv-delete" @click.stop="handleDeleteConv(c.id)"><Delete /></el-icon>
        </div>
        <div v-if="!conversations.length" style="padding: 20px; color: #909399; font-size: 13px; text-align: center">
          暂无会话
        </div>
      </div>
    </div>

    <!-- Right: Chat Area -->
    <div class="chat-main">
      <template v-if="activeConvId">
        <!-- Messages -->
        <div class="chat-messages" ref="messagesRef">
          <div v-for="task in tasks" :key="task.id" class="chat-msg" :class="'msg-user'">
            <!-- User message -->
            <div class="msg-bubble msg-user-bubble">
              <div class="msg-text">{{ task.prompt }}</div>
              <el-image
                v-if="task.uploaded_image"
                :src="task.uploaded_image"
                :preview-src-list="[task.uploaded_image]"
                style="max-width: 200px; max-height: 160px; border-radius: 6px; margin-top: 8px"
                fit="contain"
              />
            </div>
            <!-- AI response -->
            <div class="msg-bubble msg-ai-bubble" v-if="task.optimized_prompt || task.result_image_url || task.error_msg">
              <div v-if="task.status === 'generating'" style="color: #e6a23c">
                <el-icon class="is-loading"><Loading /></el-icon> 生成中...
              </div>
              <div v-if="task.optimized_prompt" class="msg-text" style="color: #303133">
                <div style="font-size: 12px; color: #909399; margin-bottom: 4px">优化后提示词：</div>
                {{ task.optimized_prompt }}
              </div>
              <el-image
                v-if="task.result_image_url"
                :src="task.result_image_url"
                :preview-src-list="[task.result_image_url]"
                style="max-width: 300px; max-height: 300px; border-radius: 6px; margin-top: 8px"
                fit="contain"
              />
              <div v-if="task.error_msg" style="color: #f56c6c; margin-top: 4px; font-size: 13px">
                {{ task.error_msg }}
              </div>
            </div>
          </div>
          <div v-if="!tasks.length" style="text-align: center; color: #c0c4cc; padding: 60px 0">
            上传商品图片或输入描述，开始生成
          </div>
        </div>

        <!-- Input Bar -->
        <div class="chat-input-bar">
          <div class="chat-input-top">
            <el-upload
              :auto-upload="false"
              :limit="1"
              accept="image/*"
              :on-change="handleFileChange"
              :on-remove="handleFileRemove"
              :file-list="fileList"
              :show-file-list="false"
            >
              <el-button :icon="'PictureFilled'" circle />
            </el-upload>
            <div v-if="selectedFile" class="file-preview">
              <img :src="filePreviewUrl" style="height: 40px; border-radius: 4px" />
              <el-icon style="cursor: pointer; color: #f56c6c" @click="handleFileRemove"><CircleClose /></el-icon>
            </div>
            <el-select
              v-model="form.model_config_id"
              placeholder="默认模型"
              clearable
              size="small"
              style="width: 180px"
            >
              <el-option
                v-for="c in modelConfigs"
                :key="c.id"
                :label="`${c.name}`"
                :value="c.id"
              />
            </el-select>
            <el-checkbox v-model="form.optimize_prompt" label="AI优化提示词" size="small" />
          </div>
          <div class="chat-input-bottom">
            <el-input
              v-model="form.prompt"
              placeholder="输入商品描述，支持多轮对话迭代优化（如：换个白色背景、光线更柔和一些）"
              @keyup.enter.native="handleGenerate"
              :disabled="generating"
            />
            <el-button
              type="primary"
              :loading="generating"
              :icon="'Promotion'"
              @click="handleGenerate"
            >
              发送
            </el-button>
          </div>
        </div>
      </template>
      <template v-else>
        <div style="display: flex; align-items: center; justify-content: center; height: 100%; color: #c0c4cc; font-size: 15px">
          ← 选择或新建一个会话开始
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, computed, watch } from 'vue'
import { conversationAPI, modelConfigAPI } from '../api'
import { ElMessage } from 'element-plus'

const form = ref({
  prompt: '',
  model_config_id: null,
  optimize_prompt: true,
})

const conversations = ref([])
const activeConvId = ref(null)
const tasks = ref([])
const generating = ref(false)
const modelConfigs = ref([])
const messagesRef = ref(null)
const fileList = ref([])
const selectedFile = ref(null)

const filePreviewUrl = computed(() => {
  if (selectedFile.value) {
    return URL.createObjectURL(selectedFile.value)
  }
  return ''
})

function handleFileChange(file) {
  selectedFile.value = file.raw
}

function handleFileRemove() {
  selectedFile.value = null
  fileList.value = []
}

async function fetchConversations() {
  try {
    const res = await conversationAPI.list()
    conversations.value = res.data
  } catch {}
}

async function fetchModelConfigs() {
  try {
    const res = await modelConfigAPI.list()
    modelConfigs.value = res.data
  } catch {}
}

async function selectConv(id) {
  activeConvId.value = id
  try {
    const res = await conversationAPI.get(id)
    tasks.value = res.data.tasks || []
    await nextTick()
    scrollToBottom()
  } catch {
    tasks.value = []
  }
}

async function handleNewConv() {
  try {
    const res = await conversationAPI.create()
    conversations.value.unshift(res.data)
    await selectConv(res.data.id)
  } catch (err) {
    ElMessage.error('创建会话失败')
  }
}

async function handleDeleteConv(id) {
  try {
    await conversationAPI.delete(id)
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (activeConvId.value === id) {
      activeConvId.value = null
      tasks.value = []
    }
  } catch {
    ElMessage.error('删除失败')
  }
}

async function handleGenerate() {
  if (!form.value.prompt.trim() && !selectedFile.value) {
    ElMessage.warning('请输入描述或上传图片')
    return
  }
  if (!activeConvId.value) return

  const fd = new FormData()
  fd.append('prompt', form.value.prompt || '请分析这张商品图片')
  fd.append('optimize_prompt', form.value.optimize_prompt)
  if (form.value.model_config_id) {
    fd.append('model_config_id', form.value.model_config_id)
  }
  if (selectedFile.value) {
    fd.append('image', selectedFile.value)
  }

  generating.value = true
  try {
    const res = await conversationAPI.generate(activeConvId.value, fd)
    tasks.value.push(res.data)
    form.value.prompt = ''
    selectedFile.value = null
    fileList.value = []
    await fetchConversations()
    await nextTick()
    scrollToBottom()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '生成失败')
  } finally {
    generating.value = false
  }
}

function scrollToBottom() {
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

onMounted(() => {
  fetchConversations()
  fetchModelConfigs()
})
</script>

<style scoped>
.chat-layout {
  display: flex;
  height: calc(100vh - 56px - 48px);
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}

.conv-sidebar {
  width: 240px;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  background: #fafafa;
}

.conv-sidebar-header {
  padding: 12px;
  border-bottom: 1px solid #e4e7ed;
}

.conv-list {
  flex: 1;
  overflow-y: auto;
}

.conv-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.15s;
}

.conv-item:hover {
  background: #ecf5ff;
}

.conv-item.active {
  background: #e1effe;
}

.conv-title {
  flex: 1;
  font-size: 13px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-delete {
  color: #c0c4cc;
  font-size: 14px;
  flex-shrink: 0;
  margin-left: 8px;
}

.conv-delete:hover {
  color: #f56c6c;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.chat-msg {
  margin-bottom: 20px;
}

.msg-bubble {
  max-width: 80%;
  padding: 12px 16px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.msg-user-bubble {
  background: #ecf5ff;
  color: #303133;
  display: inline-block;
}

.msg-ai-bubble {
  background: #f5f7fa;
  color: #606266;
  display: inline-block;
  margin-top: 8px;
}

.chat-input-bar {
  border-top: 1px solid #e4e7ed;
  padding: 12px 16px;
  background: #fff;
}

.chat-input-top {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.chat-input-bottom {
  display: flex;
  gap: 10px;
}

.file-preview {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
