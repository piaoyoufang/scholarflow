# 基础镜像：默认官方 Docker Hub。如果服务器网络受限可传入：
# --build-arg PYTHON_BASE_IMAGE=docker.1ms.run/library/python:3.12-slim
ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${PYTHON_BASE_IMAGE}

# 全局Python环境变量配置
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# 创建专用运行用户（不使用root）
RUN groupadd --gid 10001 scholarflow \
    && useradd --uid 10001 --gid scholarflow --create-home scholarflow

# 先拷依赖文件（缓存层）
COPY requirements.txt requirements.lock.txt /app/
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/requirements.lock.txt

# 拷贝业务代码
COPY app /app/app
COPY scripts /app/scripts
COPY ui.py /app/ui.py
COPY data/raw /app/data/raw
COPY data/eval /app/data/eval

# 预先创建持久化目录
RUN mkdir -p /app/data/chroma /app/data/memory /app/data/auth \
    /app/logs /app/reports \
    && chown -R scholarflow:scholarflow /app

USER scholarflow

EXPOSE 8000 8501
