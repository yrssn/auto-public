<template>
  <div class="gen-layout">
    <!-- Left: Conversation List -->
    <div class="conv-sidebar">
      <div class="conv-header">
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
          <el-icon class="conv-del" @click.stop="handleDeleteConv(c.id)"><Delete /></el-icon>
        </div>
        <div v-if="!conversations.length" class="conv-empty">暂无会话，点击上方新建</div>
      </div>
    </div>

    <!-- Right: Main Content -->
    <div class="gen-main">
      <template v-if="activeConvId">
        <!-- Results -->
        <div class="results-area" ref="resultsRef">
          <div v-if="!tasks.length && !progressMsg" class="results-empty">
            <el-icon :size="48" style="color: #dcdfe6"><PictureFilled /></el-icon>
            <p>上传商品图片或输入描述开始生成</p>
          </div>

          <div v-for="(task, idx) in tasks" :key="task.id" class="result-card">
            <div class="result-header">
              <span class="result-step">#{{ idx + 1 }}</span>
              <el-tag :type="statusType(task.status)" size="small">{{ statusLabel(task.status) }}</el-tag>
              <span class="result-time">{{ fmtTime(task.created_at) }}</span>
            </div>
            <div class="result-body">
              <div class="result-input">
                <div class="result-label">输入</div>
                <p class="result-prompt">{{ task.prompt }}</p>
                <el-image
                  v-if="task.uploaded_image"
                  :src="task.uploaded_image"
                  :preview-src-list="[task.uploaded_image]"
                  class="result-thumb"
                  fit="contain"
                />
              </div>
              <div class="result-output" v-if="task.optimized_prompt || task.result_image_url || task.error_msg">
                <div class="result-label">AI 输出</div>
                <div v-if="task.optimized_prompt" class="result-optimized">
                  <span class="opt-label">优化提示词：</span>{{ task.optimized_prompt }}
                </div>
                <div v-if="task.result_image_url" style="margin-top: 8px">
                  <span class="opt-label">生成图片：</span>
                  <el-image
                    :src="task.result_image_url"
                    :preview-src-list="[task.result_image_url]"
                    class="result-thumb-lg"
                    fit="contain"
                    style="margin-top: 4px"
                  />
                </div>
                <p v-if="task.error_msg" class="result-error">{{ task.error_msg }}</p>
              </div>
            </div>
          </div>

          <!-- Live progress indicator -->
          <div v-if="progressMsg" class="progress-bar">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>{{ progressMsg }}</span>
          </div>
        </div>

        <!-- Input Bar -->
        <div class="input-bar">
          <div class="input-bar-top">
            <el-upload
              :auto-upload="false"
              :limit="1"
              accept="image/*"
              :on-change="handleFileChange"
              :on-remove="handleFileRemove"
              :file-list="fileList"
              list-type="picture-card"
              class="img-uploader"
            >
              <el-icon :size="18"><Plus /></el-icon>
            </el-upload>
            <div class="input-fields">
              <el-input
                v-model="form.prompt"
                type="textarea"
                :rows="2"
                placeholder="输入商品描述，支持多轮迭代（换个背景 / 光线更柔和）"
                :disabled="generating"
                @keydown.enter.ctrl="handleGenerate"
              />
              <div class="input-actions">
                <el-select v-model="form.model_config_id" placeholder="默认模型" clearable size="small" style="width: 160px">
                  <el-option v-for="c in modelConfigs" :key="c.id" :label="c.name" :value="c.id" />
                </el-select>
                <el-checkbox v-model="form.optimize_prompt" size="small">AI 优化</el-checkbox>
                <div class="ws-status">
                  <span class="ws-dot" :class="wsConnected ? 'on' : 'off'"></span>
                  {{ wsConnected ? '已连接' : '未连接' }}
                </div>
                <el-button type="primary" :loading="generating" @click="handleGenerate" style="margin-left: auto">
                  <el-icon><Promotion /></el-icon> 发送
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </template>
      <template v-else>
        <div class="gen-placeholder">
          <el-icon :size="64" style="color: #e4e7ed"><ChatDotRound /></el-icon>
          <p>选择或新建一个会话开始生成</p>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { conversationAPI, modelConfigAPI, getConvWsUrl } from '../api'
import { ElMessage } from 'element-plus'

const form = ref({ prompt: '', model_config_id: null, optimize_prompt: true })
const conversations = ref([])
const activeConvId = ref(null)
const tasks = ref([])
const generating = ref(false)
const modelConfigs = ref([])
const resultsRef = ref(null)
const fileList = ref([])
const selectedFile = ref(null)
const progressMsg = ref('')
const wsConnected = ref(false)

let ws = null

const statusMap = {
  pending: { label: '等待中', type: 'info' },
  generating: { label: '生成中', type: 'warning' },
  done: { label: '完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}
function statusType(s) { return statusMap[s]?.type || 'info' }
function statusLabel(s) { return statusMap[s]?.label || s }
function fmtTime(t) { return t ? new Date(t).toLocaleString('zh-CN') : '' }

function handleFileChange(file) { selectedFile.value = file.raw }
function handleFileRemove() { selectedFile.value = null; fileList.value = [] }

// ---- WS Management ----
function connectWs(convId) {
  disconnectWs()
  const url = getConvWsUrl(convId)
  ws = new WebSocket(url)

  ws.onopen = () => { wsConnected.value = true }
  ws.onclose = () => { wsConnected.value = false; ws = null }
  ws.onerror = () => { wsConnected.value = false }

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    handleWsMessage(msg)
  }
}

function disconnectWs() {
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
    wsConnected.value = false
  }
}

function handleWsMessage(msg) {
  if (msg.type === 'task_created') {
    tasks.value.push(msg.task)
    nextTick(scrollToBottom)
  } else if (msg.type === 'progress') {
    progressMsg.value = msg.message || ''
    // Live update optimized_prompt on task
    if (msg.optimized_prompt && tasks.value.length) {
      const last = tasks.value[tasks.value.length - 1]
      last.optimized_prompt = msg.optimized_prompt
    }
    nextTick(scrollToBottom)
  } else if (msg.type === 'task_updated') {
    progressMsg.value = ''
    generating.value = false
    const idx = tasks.value.findIndex(t => t.id === msg.task.id)
    if (idx >= 0) {
      tasks.value[idx] = msg.task
    } else {
      tasks.value.push(msg.task)
    }
    fetchConversations()
    nextTick(scrollToBottom)
  } else if (msg.type === 'error') {
    progressMsg.value = ''
    generating.value = false
    ElMessage.error(msg.message)
  }
}

// ---- Data Fetching ----
async function fetchConversations() {
  try { conversations.value = (await conversationAPI.list()).data } catch {}
}
async function fetchModelConfigs() {
  try { modelConfigs.value = (await modelConfigAPI.list()).data } catch {}
}

async function selectConv(id) {
  activeConvId.value = id
  try {
    tasks.value = (await conversationAPI.get(id)).data.tasks || []
    await nextTick()
    scrollToBottom()
  } catch { tasks.value = [] }
  connectWs(id)
}

async function handleNewConv() {
  try {
    const res = await conversationAPI.create()
    conversations.value.unshift(res.data)
    await selectConv(res.data.id)
  } catch { ElMessage.error('创建会话失败') }
}

async function handleDeleteConv(id) {
  try {
    await conversationAPI.delete(id)
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (activeConvId.value === id) {
      activeConvId.value = null
      tasks.value = []
      disconnectWs()
    }
  } catch { ElMessage.error('删除失败') }
}

async function handleGenerate() {
  if (!form.value.prompt.trim() && !selectedFile.value) {
    ElMessage.warning('请输入描述或上传图片')
    return
  }
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    ElMessage.error('WebSocket 未连接，请刷新页面')
    return
  }

  generating.value = true
  progressMsg.value = '准备中...'

  // Upload image first if present
  let uploadedPath = null
  if (selectedFile.value) {
    try {
      progressMsg.value = '上传图片中...'
      const res = await conversationAPI.upload(selectedFile.value)
      uploadedPath = res.data.path
    } catch {
      ElMessage.error('图片上传失败')
      generating.value = false
      progressMsg.value = ''
      return
    }
  }

  // Send via WS
  ws.send(JSON.stringify({
    prompt: form.value.prompt || '',
    uploaded_image: uploadedPath,
    model_config_id: form.value.model_config_id,
    optimize_prompt: form.value.optimize_prompt,
  }))

  form.value.prompt = ''
  selectedFile.value = null
  fileList.value = []
}

function scrollToBottom() {
  if (resultsRef.value) resultsRef.value.scrollTop = resultsRef.value.scrollHeight
}

onMounted(() => { fetchConversations(); fetchModelConfigs() })
onUnmounted(() => { disconnectWs() })
</script>

<style scoped>
.gen-layout {
  display: flex;
  height: calc(100vh - 56px - 48px);
  background: #f5f7fa;
  border-radius: 8px;
  overflow: hidden;
}

/* ---- Sidebar ---- */
.conv-sidebar {
  width: 220px; border-right: 1px solid #e4e7ed;
  display: flex; flex-direction: column; flex-shrink: 0; background: #fff;
}
.conv-header { padding: 12px; border-bottom: 1px solid #f0f0f0; }
.conv-list { flex: 1; overflow-y: auto; }
.conv-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px; cursor: pointer; border-bottom: 1px solid #fafafa;
  transition: background 0.15s;
}
.conv-item:hover { background: #f5f7fa; }
.conv-item.active { background: #ecf5ff; border-left: 3px solid #409eff; }
.conv-title {
  flex: 1; font-size: 13px; color: #303133;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.conv-del { color: #c0c4cc; font-size: 13px; flex-shrink: 0; margin-left: 6px; }
.conv-del:hover { color: #f56c6c; }
.conv-empty { padding: 24px; color: #c0c4cc; font-size: 13px; text-align: center; }

/* ---- Main ---- */
.gen-main { flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: hidden; }
.gen-placeholder {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 12px; color: #c0c4cc; font-size: 15px;
}

/* ---- Results ---- */
.results-area { flex: 1; overflow-y: auto; padding: 16px 20px; }
.results-empty {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; gap: 12px; color: #c0c4cc;
}
.results-empty p { font-size: 14px; margin: 0; }

.result-card {
  background: #fff; border-radius: 8px; padding: 16px;
  margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.result-header {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #f5f5f5;
}
.result-step { font-weight: 600; font-size: 14px; color: #409eff; }
.result-time { margin-left: auto; font-size: 12px; color: #c0c4cc; }
.result-body { display: flex; gap: 20px; }
.result-input { flex: 1; min-width: 0; }
.result-output { flex: 1; min-width: 0; }
.result-label { font-size: 12px; color: #909399; margin-bottom: 6px; font-weight: 500; }
.result-prompt { font-size: 14px; color: #303133; margin: 0 0 8px; line-height: 1.6; word-break: break-word; }
.result-optimized { font-size: 13px; color: #606266; margin: 0 0 8px; line-height: 1.6; background: #f9fafc; padding: 8px 10px; border-radius: 6px; word-break: break-word; }
.result-error { font-size: 13px; color: #f56c6c; margin: 0; }
.opt-label { font-size: 12px; color: #909399; font-weight: 500; }
.result-thumb { max-width: 160px; max-height: 120px; border-radius: 6px; }
.result-thumb-lg { max-width: 280px; max-height: 240px; border-radius: 6px; }

/* ---- Progress ---- */
.progress-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px; background: #fdf6ec; border-radius: 8px;
  color: #e6a23c; font-size: 14px; margin-top: 8px;
}

/* ---- Input Bar ---- */
.input-bar {
  border-top: 1px solid #e4e7ed; padding: 12px 16px; background: #fff; flex-shrink: 0;
}
.input-bar-top { display: flex; gap: 12px; align-items: flex-start; }
.img-uploader { flex-shrink: 0; }
.img-uploader :deep(.el-upload--picture-card) { width: 72px; height: 72px; }
.input-fields { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.input-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.ws-status {
  display: flex; align-items: center; gap: 4px;
  font-size: 12px; color: #909399;
}
.ws-dot {
  width: 8px; height: 8px; border-radius: 50%; display: inline-block;
}
.ws-dot.on { background: #67c23a; }
.ws-dot.off { background: #f56c6c; }
</style>
