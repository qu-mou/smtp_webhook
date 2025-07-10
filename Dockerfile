FROM python:3.11-slim

WORKDIR /app

RUN  rm -rf /var/lib/apt/lists/*

COPY . /app

RUN pip install --no-cache-dir aiosmtpd requests -i https://pypi.tuna.tsinghua.edu.cn/simple

EXPOSE 25252

ENV WEBHOOK_URL=http://host.docker.internal:8080/webhook
ENV SMTP_PORT=25252

VOLUME ["/app"]

# 启动命令
CMD ["python", "-u", "smtp_webhook_docker.py"]
