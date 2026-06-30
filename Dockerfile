# ============================================================
# 前端构建阶段
# ============================================================
FROM node:22-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ============================================================
# Python 依赖构建阶段
# ============================================================
FROM python:3.12-slim AS python-builder

WORKDIR /app

# 安装系统依赖（easyocr 需要 libgl1）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ============================================================
# 运行阶段
# ============================================================
FROM python:3.12-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制 Python 包
COPY --from=python-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=python-builder /usr/local/bin /usr/local/bin

# 复制应用代码
COPY backend/ ./backend/

# 复制前端构建产物
COPY --from=frontend-builder /app/frontend/dist/ ./frontend/dist/

# 创建数据目录
RUN mkdir -p /app/memory /app/data \
    && chown -R nobody:nogroup /app/memory /app/data

USER nobody

EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2} --log-level ${LOG_LEVEL:-info}"]
