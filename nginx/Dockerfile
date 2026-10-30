# ============================================================
# Nginx 多阶段构建：
# 阶段1：用 Node.js 构建 Vue 前端 → dist/ 静态文件
# 阶段2：官方 nginx 镜像 + 拷贝 dist + 拷贝反向代理配置
# 最终镜像只有 ~30MB，包含一切
# ============================================================

# --- 阶段 1：构建 Vue 前端 ---
FROM node:20-alpine AS frontend-builder

WORKDIR /build

COPY vue-frontend/package.json vue-frontend/package-lock.json ./
RUN npm install --no-audit --no-fund --loglevel=error

COPY vue-frontend/ ./
RUN npm run build

# --- 阶段 2：Nginx 运行 ---
FROM nginx:1.27-alpine

# 删掉默认站点配置
RUN rm -f /etc/nginx/conf.d/default.conf

# 拷贝我们的反向代理配置
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf

# 拷贝公共代理请求头配置（被 nginx.conf 各 location include）
COPY nginx/proxy_params.conf /etc/nginx/proxy_params.conf

# 从阶段1拷贝构建好的前端静态文件
COPY --from=frontend-builder /build/dist /usr/share/nginx/html
