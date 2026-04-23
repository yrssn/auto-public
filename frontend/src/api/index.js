import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const isAuthRequest = err.config?.url?.startsWith('/auth/')
    if (err.response?.status === 401 && !isAuthRequest) {
      localStorage.removeItem('token')
      window.location.hash = '#/login'
    }
    return Promise.reject(err)
  }
)

// Auth
export const authAPI = {
  login: (data) => api.post('/auth/login', data),
  register: (data) => api.post('/auth/register', data),
  me: () => api.get('/auth/me'),
}

// Model Config
export const modelConfigAPI = {
  list: () => api.get('/model-configs/'),
  create: (data) => api.post('/model-configs/', data),
  update: (id, data) => api.put(`/model-configs/${id}`, data),
  delete: (id) => api.delete(`/model-configs/${id}`),
}

// Conversations
export const conversationAPI = {
  list: () => api.get('/image-gen/conversations'),
  create: () => api.post('/image-gen/conversations'),
  get: (id) => api.get(`/image-gen/conversations/${id}`),
  delete: (id) => api.delete(`/image-gen/conversations/${id}`),
  upload: (file) => {
    const fd = new FormData()
    fd.append('image', file)
    return api.post('/image-gen/upload', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}


// Ziniao
export const ziniaoAPI = {
  testConnection: () => api.get('/ziniao/test-connection'),
  getCompany: () => api.get('/ziniao/company'),
  getStaff: (page = 1, pageSize = 50) => api.get('/ziniao/staff', { params: { page, page_size: pageSize } }),
  getStores: (page = 1, pageSize = 50) => api.get('/ziniao/stores', { params: { page, page_size: pageSize } }),
}

export function getConvWsUrl(convId) {
  const token = localStorage.getItem('token')
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}/api/image-gen/conversations/${convId}/ws?token=${token}`
}

export default api
