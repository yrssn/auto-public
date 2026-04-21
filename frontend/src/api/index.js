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
    if (err.response?.status === 401) {
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

// Image Generation
export const imageGenAPI = {
  generate: (data) => api.post('/image-gen/', data),
  list: () => api.get('/image-gen/'),
  get: (id) => api.get(`/image-gen/${id}`),
}

export default api
