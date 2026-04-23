<template>
  <div class="ziniao-page">
    <!-- Step 1: Test Connection -->
    <el-card shadow="hover" class="ziniao-card">
      <template #header>
        <div class="card-header">
          <span>1. 测试连接（获取 App Token）</span>
          <el-button type="primary" :loading="loading.token" @click="handleTestConnection">
            <el-icon><Connection /></el-icon> 测试连接
          </el-button>
        </div>
      </template>
      <div v-if="results.token">
        <el-tag v-if="results.token.ok" type="success" size="large">连接成功</el-tag>
        <el-tag v-else type="danger" size="large">连接失败</el-tag>
        <div class="result-detail">
          <div v-if="results.token.app_token" class="token-display">
            <span class="label">App Token:</span>
            <el-input :model-value="results.token.app_token" readonly size="small" />
          </div>
        </div>
      </div>
      <div v-if="errors.token" class="error-msg">{{ errors.token }}</div>
    </el-card>

    <!-- Step 2: Get Company Info -->
    <el-card shadow="hover" class="ziniao-card">
      <template #header>
        <div class="card-header">
          <span>2. 获取公司信息（companyId）</span>
          <el-button type="primary" :loading="loading.company" @click="handleGetCompany">
            <el-icon><OfficeBuilding /></el-icon> 获取公司
          </el-button>
        </div>
      </template>
      <div v-if="results.company">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item v-for="(val, key) in flatCompany" :key="key" :label="key">
            {{ val }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <div v-if="errors.company" class="error-msg">{{ errors.company }}</div>
    </el-card>

    <!-- Step 3: Staff List -->
    <el-card shadow="hover" class="ziniao-card">
      <template #header>
        <div class="card-header">
          <span>3. ERP 员工查询 <el-tag v-if="staffAllRows.length" size="small" type="info">共 {{ staffAllRows.length }} 人</el-tag></span>
          <el-button type="primary" :loading="loading.staff" @click="handleGetStaff">
            <el-icon><User /></el-icon> 查询员工
          </el-button>
        </div>
      </template>
      <div v-if="staffPageRows.length">
        <el-table :data="staffPageRows" stripe size="small" max-height="400" style="width: 100%">
          <el-table-column type="index" label="#" width="50" :index="(i) => (staffPage.page - 1) * staffPage.size + i + 1" />
          <el-table-column v-for="col in staffCols" :key="col" :prop="col" :label="col" min-width="120" show-overflow-tooltip />
        </el-table>
        <el-pagination v-if="staffAllRows.length > staffPage.size" style="margin-top: 12px; justify-content: center" background layout="prev, pager, next, sizes, total" :total="staffAllRows.length" v-model:page-size="staffPage.size" v-model:current-page="staffPage.page" :page-sizes="[10, 20, 50, 100]" />
      </div>
      <div v-if="errors.staff" class="error-msg">{{ errors.staff }}</div>
    </el-card>

    <!-- Step 4: Store List -->
    <el-card shadow="hover" class="ziniao-card">
      <template #header>
        <div class="card-header">
          <span>4. ERP 店铺列表查询 <el-tag v-if="storeAllRows.length" size="small" type="info">共 {{ storeAllRows.length }} 家</el-tag></span>
          <el-button type="primary" :loading="loading.stores" @click="handleGetStores">
            <el-icon><Shop /></el-icon> 查询店铺
          </el-button>
        </div>
      </template>
      <div v-if="storePageRows.length">
        <el-table :data="storePageRows" stripe size="small" max-height="400" style="width: 100%">
          <el-table-column type="index" label="#" width="50" :index="(i) => (storePage.page - 1) * storePage.size + i + 1" />
          <el-table-column v-for="col in storeCols" :key="col" :prop="col" :label="col" min-width="120" show-overflow-tooltip />
        </el-table>
        <el-pagination v-if="storeAllRows.length > storePage.size" style="margin-top: 12px; justify-content: center" background layout="prev, pager, next, sizes, total" :total="storeAllRows.length" v-model:page-size="storePage.size" v-model:current-page="storePage.page" :page-sizes="[10, 20, 50, 100]" />
      </div>
      <div v-if="errors.stores" class="error-msg">{{ errors.stores }}</div>
    </el-card>

    <!-- Raw JSON Viewer -->
    <el-card shadow="hover" class="ziniao-card" v-if="lastRaw">
      <template #header>
        <div class="card-header">
          <span>原始返回数据</span>
          <el-button text size="small" @click="lastRaw = null">清除</el-button>
        </div>
      </template>
      <pre class="raw-json">{{ JSON.stringify(lastRaw, null, 2) }}</pre>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref, computed } from 'vue'
import { ziniaoAPI } from '../api/index.js'

const loading = reactive({ token: false, company: false, staff: false, stores: false })
const results = reactive({ token: null, company: null, staff: null, stores: null })
const errors = reactive({ token: '', company: '', staff: '', stores: '' })
const lastRaw = ref(null)

async function handleTestConnection() {
  loading.token = true; errors.token = ''; results.token = null
  try {
    const { data } = await ziniaoAPI.testConnection()
    results.token = data
    lastRaw.value = data.raw
  } catch (e) {
    errors.token = e.response?.data?.detail || e.message
  } finally { loading.token = false }
}

async function handleGetCompany() {
  loading.company = true; errors.company = ''; results.company = null
  try {
    const { data } = await ziniaoAPI.getCompany()
    results.company = data.data
    lastRaw.value = data.raw
  } catch (e) {
    errors.company = e.response?.data?.detail || e.message
  } finally { loading.company = false }
}

const flatCompany = computed(() => {
  if (!results.company) return {}
  const obj = {}
  for (const [k, v] of Object.entries(results.company)) {
    obj[k] = typeof v === 'object' ? JSON.stringify(v) : v
  }
  return obj
})

const staffPage = reactive({ page: 1, size: 20 })

async function handleGetStaff() {
  loading.staff = true; errors.staff = ''; results.staff = null; staffPage.page = 1
  try {
    const { data } = await ziniaoAPI.getStaff(1, 1000)
    results.staff = data.data
    lastRaw.value = data.raw
  } catch (e) {
    errors.staff = e.response?.data?.detail || e.message
  } finally { loading.staff = false }
}

function _extractRows(obj) {
  if (!obj) return []
  if (Array.isArray(obj)) return obj
  if (obj.data && Array.isArray(obj.data)) return obj.data
  if (obj.list && Array.isArray(obj.list)) return obj.list
  if (obj.rows && Array.isArray(obj.rows)) return obj.rows
  return []
}

function _simpleCols(rows) {
  if (!rows.length) return []
  return Object.keys(rows[0]).filter(k => {
    const v = rows[0][k]
    return v === null || v === undefined || typeof v !== 'object'
  })
}

const staffAllRows = computed(() => _extractRows(results.staff))
const staffPageRows = computed(() => {
  const start = (staffPage.page - 1) * staffPage.size
  return staffAllRows.value.slice(start, start + staffPage.size)
})
const staffCols = computed(() => _simpleCols(staffAllRows.value))

const storePage = reactive({ page: 1, size: 20 })

async function handleGetStores() {
  loading.stores = true; errors.stores = ''; results.stores = null; storePage.page = 1
  try {
    const { data } = await ziniaoAPI.getStores(1, 1000)
    results.stores = data.data
    lastRaw.value = data.raw
  } catch (e) {
    errors.stores = e.response?.data?.detail || e.message
  } finally { loading.stores = false }
}

const storeAllRows = computed(() => _extractRows(results.stores))
const storePageRows = computed(() => {
  const start = (storePage.page - 1) * storePage.size
  return storeAllRows.value.slice(start, start + storePage.size)
})
const storeCols = computed(() => _simpleCols(storeAllRows.value))
</script>

<style scoped>
.ziniao-page {
  padding: 16px;
  max-width: 960px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ziniao-card {
  width: 100%;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}
.result-detail {
  margin-top: 12px;
}
.token-display {
  display: flex;
  align-items: center;
  gap: 8px;
}
.token-display .label {
  white-space: nowrap;
  font-size: 13px;
  color: #606266;
}
.input-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.hint-msg {
  color: #909399;
  font-size: 13px;
}
.error-msg {
  margin-top: 8px;
  color: #f56c6c;
  font-size: 13px;
  word-break: break-all;
}
.raw-json {
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px;
  font-size: 12px;
  max-height: 400px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
