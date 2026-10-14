# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 依赖（PyMySQL 为纯 Python，无需编译工具链）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY migrate.py ./

# 运行期数据目录（生产建议挂载卷）
RUN mkdir -p /app/uploads/docs /app/uploads/avatars /app/logs

EXPOSE 8000

# 健康检查：命中 /api/health（返回 200 视为健康）
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
