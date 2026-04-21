import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
  },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    redirect: '/image-gen',
    children: [
      {
        path: 'model-config',
        name: 'ModelConfig',
        component: () => import('../views/ModelConfig.vue'),
        meta: { title: '模型配置' },
      },
      {
        path: 'image-gen',
        name: 'ImageGen',
        component: () => import('../views/ImageGen.vue'),
        meta: { title: '图片生成' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.name !== 'Login' && !token) {
    next({ name: 'Login' })
  } else {
    next()
  }
})

export default router
