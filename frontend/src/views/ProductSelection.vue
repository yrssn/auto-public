<template>
  <div class="ps-layout">
    <!-- Search Panel -->
    <div class="ps-search-panel">
      <el-tabs v-model="activeTab" class="ps-tabs">
        <el-tab-pane label="关键词搜索" name="keyword">
          <div class="search-row">
            <el-input
              v-model="keywordForm.keyword"
              placeholder="输入商品关键词，如：蓝牙耳机"
              clearable
              @keydown.enter="handleKeywordSearch"
            >
              <template #prepend>关键词</template>
            </el-input>
            <el-button type="primary" :loading="loading" @click="handleKeywordSearch">
              <el-icon><Search /></el-icon> 搜索
            </el-button>
          </div>
        </el-tab-pane>

        <el-tab-pane label="图片搜索" name="image">
          <div class="search-row">
            <el-input
              v-model="imageForm.imgUrl"
              placeholder="输入商品图片URL"
              clearable
              @keydown.enter="handleImageSearch"
            >
              <template #prepend>图片URL</template>
            </el-input>
            <el-button type="primary" :loading="loading" @click="handleImageSearch">
              <el-icon><Search /></el-icon> 搜索
            </el-button>
          </div>
          <div v-if="imageForm.imgUrl" class="preview-row">
            <el-image :src="imageForm.imgUrl" fit="contain" class="preview-img" />
          </div>
        </el-tab-pane>

        <el-tab-pane label="商品排行" name="rank">
          <div class="search-row">
            <el-input v-model="rankForm.categoryId" placeholder="1688目录ID" clearable style="width: 200px">
              <template #prepend>目录ID</template>
            </el-input>
            <el-select v-model="rankForm.rankType" style="width: 140px">
              <el-option label="综合排行" value="complex" />
              <el-option label="热门" value="hot" />
              <el-option label="好价格" value="goodPrice" />
            </el-select>
            <el-button type="primary" :loading="loading" @click="handleRankSearch">
              <el-icon><TrendCharts /></el-icon> 查询
            </el-button>
          </div>
        </el-tab-pane>

        <el-tab-pane label="热搜词" name="topkw">
          <div class="search-row">
            <el-input
              v-model="topKwForm.categoryId"
              placeholder="1688目录ID"
              clearable
              @keydown.enter="handleTopKeywords"
            >
              <template #prepend>目录ID</template>
            </el-input>
            <el-button type="primary" :loading="loading" @click="handleTopKeywords">
              <el-icon><Search /></el-icon> 查询
            </el-button>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- Results Area -->
    <div class="ps-results">
      <!-- Error -->
      <el-alert v-if="errorMsg" :title="errorMsg" type="error" show-icon closable @close="errorMsg = ''" style="margin-bottom: 12px" />

      <!-- Top Keywords Result -->
      <div v-if="topKeywords.length" class="top-kw-section">
        <div class="section-title">热搜词</div>
        <div class="kw-tags">
          <el-tag
            v-for="(kw, idx) in topKeywords"
            :key="idx"
            class="kw-tag"
            effect="plain"
            @click="quickKeywordSearch(typeof kw === 'string' ? kw : kw.keyword || kw)"
            style="cursor: pointer"
          >
            {{ typeof kw === 'string' ? kw : kw.keyword || kw }}
          </el-tag>
        </div>
      </div>

      <!-- Product Grid -->
      <div v-if="products.length" class="product-grid">
        <div
          v-for="item in products"
          :key="item.productId || item.offerId || item.id"
          class="product-card"
          @click="handleViewDetail(item.productId || item.offerId || item.id)"
        >
          <div class="product-img-wrap">
            <el-image
              :src="item.imageUrl || item.productImage || item.image || item.imgUrl"
              fit="contain"
              class="product-img"
              lazy
            >
              <template #error>
                <div class="img-placeholder">
                  <el-icon :size="32"><PictureFilled /></el-icon>
                </div>
              </template>
            </el-image>
          </div>
          <div class="product-info">
            <div class="product-title" :title="item.subject || item.title || item.productTitle">
              {{ item.subject || item.title || item.productTitle || '未知商品' }}
            </div>
            <div class="product-meta">
              <span v-if="item.price || item.priceInfo" class="product-price">
                ¥{{ item.price || item.priceInfo?.price || '-' }}
              </span>
              <span v-if="item.productId || item.offerId" class="product-id">
                ID: {{ item.productId || item.offerId }}
              </span>
            </div>
          </div>
          <div class="product-actions">
            <el-button size="small" text type="primary" @click.stop="handleViewDetail(item.productId || item.offerId || item.id)">
              详情
            </el-button>
            <el-button size="small" text type="success" @click.stop="handleRecommend(item.productId || item.offerId || item.id)">
              相似推荐
            </el-button>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="!products.length && !topKeywords.length && !loading && !errorMsg" class="ps-empty">
        <el-icon :size="48" style="color: #dcdfe6"><Search /></el-icon>
        <p>输入关键词或图片URL开始搜索1688商品</p>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="ps-loading">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <span>正在查询 MCP 服务...</span>
      </div>

      <!-- Pagination -->
      <div v-if="products.length && currentPage > 0" class="ps-pagination">
        <el-button :disabled="currentPage <= 1" @click="handlePageChange(currentPage - 1)">上一页</el-button>
        <span class="page-info">第 {{ currentPage }} 页</span>
        <el-button :disabled="currentPage >= 10" @click="handlePageChange(currentPage + 1)">下一页</el-button>
      </div>
    </div>

    <!-- Product Detail Drawer -->
    <el-drawer v-model="detailVisible" title="商品详情" size="480px" direction="rtl">
      <div v-if="detailLoading" style="text-align: center; padding: 40px">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <p>加载中...</p>
      </div>
      <div v-else-if="productDetail" class="detail-content">
        <div v-if="productDetail.subject || productDetail.title" class="detail-title">
          {{ productDetail.subject || productDetail.title }}
        </div>
        <!-- Images -->
        <div v-if="detailImages.length" class="detail-images">
          <el-image
            v-for="(img, idx) in detailImages"
            :key="idx"
            :src="img"
            :preview-src-list="detailImages"
            fit="contain"
            class="detail-img"
            lazy
          />
        </div>
        <!-- Price -->
        <div v-if="productDetail.price || productDetail.priceInfo" class="detail-price">
          ¥{{ productDetail.price || productDetail.priceInfo?.price || '-' }}
        </div>
        <!-- SKU list -->
        <div v-if="productDetail.skuList?.length || productDetail.skuInfos?.length" class="detail-section">
          <div class="detail-label">SKU 信息</div>
          <el-table :data="productDetail.skuList || productDetail.skuInfos" size="small" max-height="300" stripe>
            <el-table-column prop="skuId" label="SKU ID" width="100" />
            <el-table-column prop="specId" label="规格" />
            <el-table-column prop="price" label="价格" width="80" />
            <el-table-column prop="amountOnSale" label="库存" width="60" />
          </el-table>
        </div>
        <!-- Raw JSON fallback -->
        <div class="detail-section">
          <div class="detail-label">原始数据</div>
          <el-input type="textarea" :rows="10" :model-value="JSON.stringify(productDetail, null, 2)" readonly />
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { productSelectionAPI } from '../api'
import { ElMessage } from 'element-plus'

const activeTab = ref('keyword')
const loading = ref(false)
const errorMsg = ref('')
const products = ref([])
const topKeywords = ref([])
const currentPage = ref(1)
const lastSearchType = ref('')
const lastSearchParams = ref({})

// Forms
const keywordForm = ref({ keyword: '' })
const imageForm = ref({ imgUrl: '' })
const rankForm = ref({ categoryId: '', rankType: 'complex' })
const topKwForm = ref({ categoryId: '' })

// Detail drawer
const detailVisible = ref(false)
const detailLoading = ref(false)
const productDetail = ref(null)
const detailImages = ref([])

// ---- Search handlers ----
async function handleKeywordSearch(page = 1) {
  const kw = keywordForm.value.keyword.trim()
  if (!kw) return ElMessage.warning('请输入关键词')
  await doSearch('keyword', { keyword: kw }, page)
}

async function handleImageSearch(page = 1) {
  const url = imageForm.value.imgUrl.trim()
  if (!url) return ElMessage.warning('请输入图片URL')
  await doSearch('image', { imgUrl: url }, page)
}

async function handleRankSearch() {
  const cid = rankForm.value.categoryId.trim()
  if (!cid) return ElMessage.warning('请输入目录ID')
  await doSearch('rank', { categoryId: cid, rankType: rankForm.value.rankType }, 0)
}

async function handleTopKeywords() {
  const cid = topKwForm.value.categoryId.trim()
  if (!cid) return ElMessage.warning('请输入目录ID')
  loading.value = true
  errorMsg.value = ''
  topKeywords.value = []
  try {
    const res = await productSelectionAPI.getTopKeywords(cid)
    const data = res.data?.data
    if (Array.isArray(data)) {
      topKeywords.value = data
    } else if (data?.keywords) {
      topKeywords.value = data.keywords
    } else if (data?.data) {
      topKeywords.value = Array.isArray(data.data) ? data.data : [data.data]
    } else {
      topKeywords.value = [data]
    }
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || e.message || '查询失败'
  } finally {
    loading.value = false
  }
}

async function doSearch(type, params, page) {
  loading.value = true
  errorMsg.value = ''
  products.value = []
  currentPage.value = typeof page === 'number' ? page : 1
  lastSearchType.value = type
  lastSearchParams.value = params

  try {
    let res
    if (type === 'keyword') {
      res = await productSelectionAPI.searchByKeyword(params.keyword, currentPage.value)
    } else if (type === 'image') {
      res = await productSelectionAPI.searchByImage(params.imgUrl, currentPage.value)
    } else if (type === 'rank') {
      res = await productSelectionAPI.getProductRank(params.categoryId, params.rankType)
    } else if (type === 'recommend') {
      res = await productSelectionAPI.getRecommend(params.productId, currentPage.value)
    }

    const data = res.data?.data
    if (Array.isArray(data)) {
      products.value = data
    } else if (data?.products || data?.result || data?.data) {
      const list = data.products || data.result || data.data
      products.value = Array.isArray(list) ? list : [list]
    } else if (data) {
      products.value = [data]
    }

    if (!products.value.length) {
      ElMessage.info('未找到商品')
    }
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || e.message || '搜索失败'
  } finally {
    loading.value = false
  }
}

function handlePageChange(page) {
  if (lastSearchType.value && lastSearchParams.value) {
    doSearch(lastSearchType.value, lastSearchParams.value, page)
  }
}

function quickKeywordSearch(kw) {
  keywordForm.value.keyword = kw
  activeTab.value = 'keyword'
  handleKeywordSearch(1)
}

// ---- Detail ----
async function handleViewDetail(productId) {
  if (!productId) return ElMessage.warning('无商品ID')
  detailVisible.value = true
  detailLoading.value = true
  productDetail.value = null
  detailImages.value = []

  try {
    const res = await productSelectionAPI.getProductDetail(String(productId))
    const data = res.data?.data
    productDetail.value = data || {}
    // Extract images
    const imgs = data?.imageList || data?.images || data?.productImage
    if (Array.isArray(imgs)) {
      detailImages.value = imgs.map(i => typeof i === 'string' ? i : i.url || i.imageUrl || '')
    } else if (typeof imgs === 'string') {
      detailImages.value = [imgs]
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '查询详情失败')
    detailVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

async function handleRecommend(productId) {
  if (!productId) return ElMessage.warning('无商品ID')
  await doSearch('recommend', { productId: String(productId) }, 1)
}
</script>

<style scoped>
.ps-layout {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px - 48px);
  background: #f5f7fa;
  border-radius: 8px;
  overflow: hidden;
}

.ps-search-panel {
  background: #fff;
  padding: 16px 20px 0;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}

.ps-tabs :deep(.el-tabs__header) { margin-bottom: 0; }

.search-row {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 14px;
}

.preview-row {
  margin-bottom: 12px;
}
.preview-img {
  max-width: 200px;
  max-height: 120px;
  border-radius: 6px;
  border: 1px solid #eee;
}

/* Results */
.ps-results {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

/* Top Keywords */
.top-kw-section {
  margin-bottom: 16px;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}
.kw-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.kw-tag:hover {
  color: #409eff;
  border-color: #409eff;
}

/* Product Grid */
.product-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 14px;
}

.product-card {
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  cursor: pointer;
  transition: box-shadow 0.2s, transform 0.15s;
  display: flex;
  flex-direction: column;
}
.product-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  transform: translateY(-2px);
}

.product-img-wrap {
  width: 100%;
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fafafa;
}
.product-img {
  max-width: 100%;
  max-height: 100%;
}
.img-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: #dcdfe6;
}

.product-info {
  padding: 10px 12px;
  flex: 1;
}
.product-title {
  font-size: 13px;
  color: #303133;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.product-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.product-price {
  font-size: 15px;
  font-weight: 600;
  color: #f56c6c;
}
.product-id {
  font-size: 11px;
  color: #c0c4cc;
}

.product-actions {
  display: flex;
  gap: 4px;
  padding: 0 8px 8px;
}

/* Empty / Loading */
.ps-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  gap: 12px;
  color: #c0c4cc;
  font-size: 14px;
}
.ps-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px;
  color: #e6a23c;
  font-size: 14px;
}

/* Pagination */
.ps-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 16px 0;
}
.page-info {
  font-size: 13px;
  color: #606266;
}

/* Detail Drawer */
.detail-content {
  padding: 0 4px;
}
.detail-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
  line-height: 1.5;
}
.detail-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.detail-img {
  width: 120px;
  height: 120px;
  border-radius: 6px;
  border: 1px solid #eee;
}
.detail-price {
  font-size: 20px;
  font-weight: 600;
  color: #f56c6c;
  margin-bottom: 16px;
}
.detail-section {
  margin-bottom: 16px;
}
.detail-label {
  font-size: 13px;
  font-weight: 600;
  color: #909399;
  margin-bottom: 6px;
}
</style>
