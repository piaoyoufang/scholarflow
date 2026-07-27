# 基础镜像：默认通过当前网络可访问的Docker Hub镜像加速地址拉取。
# 网络能够直连Docker Hub时，可在构建时传入：
# --build-arg PYTHON_BASE_IMAGE=python:3.11-slim
ARG PYTHON_BASE_IMAGE=docker.1ms.run/library/python:3.11-slim
FROM ${PYTHON_BASE_IMAGE}

# 全局Python环境变量配置
# PYTHONDONTWRITEBYTECODE=1：禁止自动生成.pyc字节码缓存文件，减少镜像体积
# PYTHONUNBUFFERED=1：关闭输出缓冲区，日志实时打印，容器日志可即时查看
# PYTHONPATH=/app：将项目根目录加入Python搜索路径，全局import app模块无需额外配置
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 设置容器内工作目录，后续所有命令默认执行路径为/app
WORKDIR /app

# 创建专用运行用户与用户组，遵循容器最小权限原则，不使用root运行服务
# groupadd --gid 10001 scholarflow：新建用户组scholarflow，组ID固定10001
# useradd --uid 10001 --gid scholarflow --create-home scholarflow：新建普通用户scholarflow，绑定上述用户组并创建家目录
RUN groupadd --gid 10001 scholarflow \
    && useradd --uid 10001 --gid scholarflow --create-home scholarflow
# COPY指令：批量拷贝宿主机两个依赖文件到容器/app路径下
# requirements.txt：开发者维护的宽松依赖版本（如 fastapi>=0.100）
# requirements.lock.txt：锁文件，精确记录每一个包的固定版本，保证环境完全一致
COPY requirements.txt requirements.lock.txt /app/
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/requirements.lock.txt


# 拷贝项目业务代码、脚本、入口文件、持久化原始数据目录至容器工作目录
COPY app /app/app
COPY scripts /app/scripts
COPY ui.py /app/ui.py
COPY data/raw /app/data/raw
COPY data/eval /app/data/eval

# 预先创建运行所需持久化目录：向量库、会话断点库、认证库、日志、报表目录
# chown -R scholarflow:scholarflow /app：将/app下所有文件归属权改为普通运行用户，避免权限报错
RUN mkdir -p /app/data/chroma /app/data/memory /app/data/auth \
    /app/logs /app/reports \
    && chown -R scholarflow:scholarflow /app

# 切换至普通非root用户启动程序，降低容器提权、文件越权读写安全风险
USER scholarflow

# 声明容器对外暴露端口：8000后端FastAPI接口、8501 Streamlit前端UI
EXPOSE 8000 8501
