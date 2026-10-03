FROM python:3.12-slim
WORKDIR /srv/app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
# 运行参数的唯一来源，随镜像带入；compose 里也会挂载同名文件保持同步
COPY runtime.json ./runtime.json
EXPOSE 8000
# 监听地址由 app.serve 从 runtime.json 解析（容器内用 APP_HOST=0.0.0.0 覆盖）
CMD ["python", "-m", "app.serve"]
