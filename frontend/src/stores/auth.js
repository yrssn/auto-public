import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authAPI } from '../api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const token = ref(localStorage.getItem('token') || '')

  const isLoggedIn = () => !!token.value

  async function login(username, password) {
    const res = await authAPI.login({ username, password })
    token.value = res.data.access_token
    localStorage.setItem('token', token.value)
  }

  async function register(username, password) {
    await authAPI.register({ username, password })
  }

  async function fetchUser() {
    try {
      const res = await authAPI.me()
      user.value = res.data
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
  }

  return { user, token, isLoggedIn, login, register, fetchUser, logout }
})
