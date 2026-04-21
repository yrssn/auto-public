<template>
  <div class="login-container">
    <div class="login-card">
      <h2>电商选品系统</h2>
      <el-form :model="form" @submit.prevent="handleSubmit">
        <el-form-item>
          <el-input
            v-model="form.username"
            placeholder="用户名"
            prefix-icon="User"
            size="large"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            prefix-icon="Lock"
            size="large"
            show-password
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            style="width: 100%"
            :loading="loading"
            @click="handleSubmit"
          >
            {{ isRegister ? '注 册' : '登 录' }}
          </el-button>
        </el-form-item>
        <div style="text-align: center">
          <el-link type="primary" @click="isRegister = !isRegister">
            {{ isRegister ? '已有账号？去登录' : '没有账号？去注册' }}
          </el-link>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()

const form = ref({ username: '', password: '' })
const isRegister = ref(false)
const loading = ref(false)

async function handleSubmit() {
  if (!form.value.username || !form.value.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    if (isRegister.value) {
      await authStore.register(form.value.username, form.value.password)
      ElMessage.success('注册成功，请登录')
      isRegister.value = false
    } else {
      await authStore.login(form.value.username, form.value.password)
      ElMessage.success('登录成功')
      router.push('/')
    }
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '操作失败')
  } finally {
    loading.value = false
  }
}
</script>
