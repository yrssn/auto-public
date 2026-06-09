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
            <p>上传产品图片开始生成</p>
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
                <!-- Product images (support multiple) -->
                <div v-if="task.uploaded_images?.product_images?.length" class="img-group">
                  <span class="img-group-label">产品图 ({{ task.uploaded_images.product_images.length }} 张)</span>
                  <div class="uploaded-images-row">
                    <el-image
                      v-for="(img, i) in task.uploaded_images.product_images"
                      :key="i"
                      :src="img"
                      :preview-src-list="task.uploaded_images.product_images"
                      :initial-index="i"
                      class="result-thumb"
                      fit="contain"
                    />
                  </div>
                </div>
                <div v-else-if="task.uploaded_images?.product_image" class="img-group">
                  <span class="img-group-label">产品图</span>
                  <el-image
                    :src="task.uploaded_images.product_image"
                    :preview-src-list="[task.uploaded_images.product_image]"
                    class="result-thumb"
                    fit="contain"
                  />
                </div>
                <el-image
                  v-else-if="task.uploaded_image"
                  :src="task.uploaded_image"
                  :preview-src-list="[task.uploaded_image]"
                  class="result-thumb"
                  fit="contain"
                />
              </div>
              <!-- Error message (always visible when failed) -->
              <div v-if="task.status === 'failed' && task.error_msg" class="result-error-block">
                <el-icon style="color: #f56c6c; margin-right: 4px"><WarningFilled /></el-icon>
                <span>{{ task.error_msg }}</span>
              </div>
              <div class="result-output" v-if="task.optimized_prompt || task.result_image_url || task.image_results?.length">
                <div class="result-label">AI 输出</div>
                <div v-if="task.optimized_prompt" class="result-optimized">
                  <span class="opt-label">优化提示词：</span>{{ task.optimized_prompt }}
                </div>
                <!-- Multi-model results -->
                <div v-if="task.image_results?.length" class="multi-image-grid">
                  <div v-for="(img, i) in task.image_results" :key="i" class="multi-image-card">
                    <div class="multi-image-model">{{ img.model_name }}<span v-if="task.image_results.length > 1"> · 第 {{ i + 1 }} 张</span></div>
                    <el-image
                      v-if="img.image_url"
                      :src="img.image_url"
                      :preview-src-list="task.image_results.filter(r => r.image_url).map(r => r.image_url)"
                      :initial-index="task.image_results.filter(r => r.image_url).findIndex(r => r.image_url === img.image_url)"
                      class="result-thumb-lg"
                      fit="contain"
                    />
                    <div v-if="img.prompt && task.image_results.length > 1" class="multi-image-prompt" :title="img.prompt">{{ img.prompt }}</div>
                    <div v-if="img.error" class="result-error-detail">
                      <el-icon style="color: #f56c6c; margin-right: 4px"><WarningFilled /></el-icon>
                      <span>{{ img.error }}</span>
                    </div>
                  </div>
                </div>
                <!-- Single model result (backward compat) -->
                <div v-else-if="task.result_image_url" style="margin-top: 8px">
                  <span class="opt-label">生成图片：</span>
                  <el-image
                    :src="task.result_image_url"
                    :preview-src-list="[task.result_image_url]"
                    class="result-thumb-lg"
                    fit="contain"
                    style="margin-top: 4px"
                  />
                </div>
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
            <!-- 产品图（支持多张） -->
            <div class="upload-group">
              <div class="upload-label">产品图（可多张）</div>
              <el-upload
                :auto-upload="false"
                :limit="5"
                accept="image/*"
                :on-change="handleProductChange"
                :on-remove="handleProductRemove"
                :file-list="productFileList"
                list-type="picture-card"
                class="img-uploader"
              >
                <el-icon :size="16"><Goods /></el-icon>
              </el-upload>
            </div>
            <div class="input-fields">
              <el-input
                v-model="form.prompt"
                type="textarea"
                :rows="2"
                placeholder="输入商品描述（可选）"
                :disabled="generating"
                @keydown.enter.ctrl="handleGenerate"
              />
              <div class="input-actions">
                <el-select v-model="form.model_config_ids" placeholder="选择图片模型（可多选）" multiple collapse-tags collapse-tags-tooltip size="small" style="min-width: 200px; max-width: 360px">
                  <el-option v-for="c in imageModels" :key="c.id" :label="c.name" :value="c.id" />
                </el-select>
                <el-select v-model="form.n" size="small" style="width: 90px">
                  <el-option :value="1" label="1张" />
                  <el-option :value="2" label="2张" />
                  <el-option :value="4" label="4张" />
                </el-select>
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

const form = ref({ prompt: '', model_config_ids: [], optimize_prompt: false, n: 1 })
const conversations = ref([])
const activeConvId = ref(null)
const tasks = ref([])
const generating = ref(false)
const modelConfigs = ref([])
const imageModels = ref([])
const resultsRef = ref(null)
// Product images (support multiple)
const productFileList = ref([])
const productFiles = ref([])
const progressMsg = ref('')
const wsConnected = ref(false)

// Map of convId -> WebSocket, supports multiple concurrent WS connections
const wsMap = new Map()
let activeWs = null
// Fallback poller: when a tab is backgrounded the WS that started a generation
// is torn down, and a freshly reconnected WS never receives that task's final
// `task_updated`. Polling the conversation REST endpoint re-syncs the final
// state so the UI doesn't stay stuck on "生成中".
let pollTimer = null

const statusMap = {
  pending: { label: '等待中', type: 'info' },
  generating: { label: '生成中', type: 'warning' },
  done: { label: '完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}
function statusType(s) { return statusMap[s]?.type || 'info' }
function statusLabel(s) { return statusMap[s]?.label || s }
function fmtTime(t) { return t ? new Date(t).toLocaleString('zh-CN') : '' }

// Product image handlers (multiple)
function handleProductChange(file, fileList) {
  productFiles.value = fileList.map(f => f.raw || f)
}
function handleProductRemove(file, fileList) {
  productFiles.value = fileList.map(f => f.raw || f)
}

// ---- WS Management ----
function connectWs(convId) {
  // Reuse existing connection if available
  if (wsMap.has(convId) && wsMap.get(convId).readyState === WebSocket.OPEN) {
    activeWs = wsMap.get(convId)
    wsConnected.value = true
    return
  }
  const url = getConvWsUrl(convId)
  const socket = new WebSocket(url)
  wsMap.set(convId, socket)
  activeWs = socket

  socket.onopen = () => {
    if (activeConvId.value === convId) wsConnected.value = true
  }
  socket.onclose = () => {
    wsMap.delete(convId)
    if (activeConvId.value === convId) wsConnected.value = false
    if (activeWs === socket) activeWs = null
  }
  socket.onerror = () => {
    if (activeConvId.value === convId) wsConnected.value = false
  }

  socket.onmessage = (e) => {
    const msg = JSON.parse(e.data)
    handleWsMessage(msg, convId)
  }
}

function disconnectWs(convId) {
  if (convId != null) {
    const socket = wsMap.get(convId)
    if (socket) {
      socket.onclose = null
      socket.close()
      wsMap.delete(convId)
      if (activeWs === socket) activeWs = null
    }
  } else {
    // Disconnect all
    for (const [, socket] of wsMap) {
      socket.onclose = null
      socket.close()
    }
    wsMap.clear()
    activeWs = null
  }
  wsConnected.value = false
}

function handleWsMessage(msg, convId) {
  const isActive = convId === activeConvId.value
  if (msg.type === 'task_created') {
    if (isActive) {
      tasks.value.push(msg.task)
      nextTick(scrollToBottom)
    }
  } else if (msg.type === 'progress') {
    if (isActive) {
      progressMsg.value = msg.message || ''
      if (msg.optimized_prompt && tasks.value.length) {
        const last = tasks.value[tasks.value.length - 1]
        last.optimized_prompt = msg.optimized_prompt
      }
      nextTick(scrollToBottom)
    }
  } else if (msg.type === 'task_updated') {
    if (isActive) {
      progressMsg.value = ''
      generating.value = false
      const idx = tasks.value.findIndex(t => t.id === msg.task.id)
      if (idx >= 0) {
        tasks.value[idx] = msg.task
      } else {
        tasks.value.push(msg.task)
      }
      // WS delivered the final state; the fallback poller is no longer needed.
      if (!tasks.value.some(t => t.status === 'generating')) stopPolling()
      nextTick(scrollToBottom)
    }
    fetchConversations()
  } else if (msg.type === 'error') {
    if (isActive) {
      progressMsg.value = ''
      generating.value = false
      ElMessage.error(msg.message)
    }
  }
}

// ---- Data Fetching ----
async function fetchConversations() {
  try { conversations.value = (await conversationAPI.list()).data } catch {}
}
async function fetchModelConfigs() {
  try {
    const all = (await modelConfigAPI.list()).data
    modelConfigs.value = all
    imageModels.value = all.filter(c => c.model_type === 'image')
  } catch {}
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

// Poll the conversation until no task is still "generating", then clear the
// in-progress UI. Used as a fallback for results that completed while the tab
// was backgrounded (the WS that started them is gone, so no `task_updated`).
function startPolling(convId) {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (activeConvId.value !== convId) { stopPolling(); return }
    try {
      const fresh = (await conversationAPI.get(convId)).data.tasks || []
      if (activeConvId.value !== convId) { stopPolling(); return }
      tasks.value = fresh
      if (!fresh.some(t => t.status === 'generating')) {
        generating.value = false
        progressMsg.value = ''
        stopPolling()
      }
    } catch { /* keep polling; transient errors are fine */ }
  }, 3000)
}

async function selectConv(id) {
  activeConvId.value = id
  stopPolling()
  try {
    tasks.value = (await conversationAPI.get(id)).data.tasks || []
    await nextTick()
    scrollToBottom()
  } catch { tasks.value = [] }
  connectWs(id)
  // Update activeWs and wsConnected
  activeWs = wsMap.get(id) || null
  wsConnected.value = activeWs?.readyState === WebSocket.OPEN
  // Check if there are tasks still generating (backend may still be running them)
  const hasGenerating = tasks.value.some(t => t.status === 'generating')
  if (hasGenerating) {
    generating.value = true
    progressMsg.value = '生成中...'
    // The originating WS may be gone (tab was backgrounded); poll for the final
    // state so the UI doesn't stay stuck on "生成中".
    startPolling(id)
  } else {
    progressMsg.value = ''
    generating.value = false
  }
}

async function handleNewConv() {
  generating.value = false
  progressMsg.value = ''
  try {
    const res = await conversationAPI.create()
    conversations.value.unshift(res.data)
    await selectConv(res.data.id)
  } catch (e) {
    console.error('创建会话失败:', e)
    ElMessage.error('创建会话失败: ' + (e?.response?.data?.detail || e?.message || '未知错误'))
  }
}

async function handleDeleteConv(id) {
  try {
    await conversationAPI.delete(id)
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (activeConvId.value === id) {
      activeConvId.value = null
      tasks.value = []
      stopPolling()
      disconnectWs(id)
    } else {
      disconnectWs(id)
    }
  } catch { ElMessage.error('删除失败') }
}

async function handleGenerate() {
  const hasProduct = productFiles.value.length > 0
  const hasPrompt = form.value.prompt.trim()

  if (!hasPrompt && !hasProduct) {
    ElMessage.warning('请上传产品图片或输入描述')
    return
  }
  if (!activeWs || activeWs.readyState !== WebSocket.OPEN) {
    ElMessage.error('WebSocket 未连接，请刷新页面')
    return
  }

  generating.value = true
  progressMsg.value = '准备中...'

  // Upload product images (support multiple)
  let productPaths = []
  if (hasProduct) {
    try {
      progressMsg.value = `上传产品图 (${productFiles.value.length} 张)...`
      for (const file of productFiles.value) {
        const res = await conversationAPI.upload(file)
        productPaths.push(res.data.path)
      }
    } catch {
      ElMessage.error('产品图上传失败')
      generating.value = false
      progressMsg.value = ''
      return
    }
  }

  // Send via WS (send both product_images array and legacy product_image)
  activeWs.send(JSON.stringify({
    prompt: form.value.prompt || '',
    product_image: productPaths.length > 0 ? productPaths[0] : null,
    product_images: productPaths.length > 0 ? productPaths : null,
    model_config_ids: form.value.model_config_ids,
    optimize_prompt: false,
    n: form.value.n,
  }))

  form.value.prompt = ''
  productFiles.value = []
  productFileList.value = []
}

function scrollToBottom() {
  if (resultsRef.value) resultsRef.value.scrollTop = resultsRef.value.scrollHeight
}

onMounted(() => { fetchConversations(); fetchModelConfigs() })
onUnmounted(() => { stopPolling(); disconnectWs() /* disconnect all */ })
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
.result-error-block {
  display: flex; align-items: flex-start; gap: 4px;
  padding: 10px 12px; background: #fef0f0; border: 1px solid #fbc4c4;
  border-radius: 6px; color: #f56c6c; font-size: 13px; line-height: 1.6;
  word-break: break-word;
}
.result-error-detail {
  display: flex; align-items: flex-start; gap: 4px;
  padding: 6px 8px; background: #fef0f0; border-radius: 4px;
  color: #f56c6c; font-size: 12px; line-height: 1.5;
  word-break: break-word; margin-top: 4px;
}
.opt-label { font-size: 12px; color: #909399; font-weight: 500; }
.result-thumb { max-width: 160px; max-height: 120px; border-radius: 6px; }
.uploaded-images-row { display: flex; flex-wrap: wrap; gap: 8px; }
.uploaded-images-section { display: flex; flex-direction: column; gap: 8px; }
.img-group { display: flex; flex-direction: column; gap: 4px; }
.img-group-label { font-size: 11px; color: #909399; font-weight: 500; }
.upload-tip { font-size: 11px; color: #909399; text-align: center; margin-top: 4px; }
.result-thumb-lg { max-width: 280px; max-height: 240px; border-radius: 6px; }

/* Multi-model image grid */
.multi-image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  margin-top: 8px;
}
.multi-image-card {
  background: #fafbfc;
  border-radius: 8px;
  padding: 8px;
  border: 1px solid #f0f0f0;
}
.multi-image-model {
  font-size: 12px;
  font-weight: 600;
  color: #409eff;
  margin-bottom: 6px;
  text-align: center;
}
.multi-image-prompt {
  font-size: 11px;
  color: #909399;
  margin-top: 6px;
  line-height: 1.5;
  max-height: 4.5em;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  word-break: break-word;
}

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
.img-uploader :deep(.el-upload--picture-card) { width: 64px; height: 64px; }
.upload-group { display: flex; flex-direction: column; gap: 4px; }
.upload-label { font-size: 11px; color: #909399; text-align: center; }
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
