# 使用官方 Python 镜像作为基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 安装 uv 并用其安装依赖
# uv 是一个快速的 Python 包安装器
RUN pip install uv
RUN uv pip install --system --no-cache --locked

# 将当前目录内容复制到容器的 /app 目录
COPY . .

# 暴露端口，让容器外的服务可以访问
EXPOSE 8000

# 运行应用的命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]