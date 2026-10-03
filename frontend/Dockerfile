FROM node:20-alpine
WORKDIR /srv/web
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
# 运行参数的唯一来源，放在 vite.config.ts 的 ../runtime.json 位置
COPY runtime.json /srv/runtime.json
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
