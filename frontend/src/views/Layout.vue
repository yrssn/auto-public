<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="sidebar-header">选品系统</div>
      <nav class="sidebar-menu">
        <router-link
          v-for="item in menuItems"
          :key="item.path"
          :to="item.path"
          class="sidebar-item"
          active-class="active"
        >
          <el-icon :size="18"><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <el-button text style="color: rgba(255,255,255,0.6)" @click="handleLogout">
          <el-icon><SwitchButton /></el-icon>
          <span style="margin-left: 6px">退出登录</span>
        </el-button>
      </div>
    </aside>
    <div class="main-area">
      <header class="topbar">
        <span class="topbar-title">{{ currentTitle }}</span>
        <span style="font-size: 13px; color: #909399">
          {{ authStore.user?.username }}
        </span>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

authStore.fetchUser()

const menuItems = [
  { path: '/image-gen', label: '图片生成', icon: 'PictureFilled' },
  { path: '/product-selection', label: '选品', icon: 'ShoppingCart' },
  { path: '/ziniao', label: '紫鸟自动化', icon: 'Monitor' },
  { path: '/model-config', label: '模型配置', icon: 'Setting' },
]

const currentTitle = computed(() => route.meta?.title || '首页')

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>
