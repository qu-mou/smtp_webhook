# -*- coding: utf-8 -*-
"""
    SMTP Server with Webhook Forwarding
    This script implements a simple SMTP server that forwards received emails
    to a specified webhook URL, logging the details of each email.
"""
import time
from aiosmtpd.controller import Controller
import requests
import logging
import email
from email.header import decode_header
from email.utils import parseaddr
import os,socket
import threading
from datetime import datetime, timedelta

# 配置日志，写入文件和控制台
log_path = os.path.join(os.path.dirname(__file__), "smtp.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# 从环境变量获取配置
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'http://localhost:8080/webhook')
SMTP_PORT = int(os.getenv('SMTP_PORT', '25252'))


class WebhookForwarder:
    def __init__(self, webhook_url, cache, lock):
        self.webhook_url = webhook_url
        self.cache = cache
        self.lock = lock

    async def handle_DATA(self, server, session, envelope):
        msg_bytes = envelope.content
        msg = email.message_from_bytes(msg_bytes)

        # 解析发件人
        sender = parseaddr(msg.get('From'))[1]
        # 解析收件人
        recipients = [parseaddr(addr)[1] for addr in msg.get_all('To', [])]

        # 解析主题并解码
        subject = msg.get('Subject', '')
        decoded_subject = ''
        for s, enc in decode_header(subject):
            if isinstance(s, bytes):
                decoded_subject += s.decode(enc or 'utf-8', errors='replace')
            else:
                decoded_subject += s

        # 解析正文
        body = ''
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    charset = part.get_content_charset() or 'utf-8'
                    body = part.get_payload(decode=True).decode(charset, errors='replace')
                    break
        else:
            charset = msg.get_content_charset() or 'utf-8'
            body = msg.get_payload(decode=True).decode(charset, errors='replace')

        logger.info(f"Received message from: {sender}")
        logger.info(f"Recipients: {', '.join(recipients)}")
        logger.info(f"Subject: {decoded_subject}")
        logger.info(f"Body: \n{body[:200]}")  # 只记录前200字符
        
        
    
        #转发到 webhook
        try:
            response = requests.post(
                self.webhook_url,
                json={
                    "msgtype": "text",
                    "text": {
                        "content": f"from {sender} \nto {', '.join(recipients)} \nsubject: {decoded_subject}\n\n{body}"
                    },
                },
                timeout=10
            )
            if response.status_code == 200:
                logger.info('200 Webhook通知已发送')
            else:
                logger.info('550 Failed to deliver to webhook')
        except Exception as e:
            logger.error(f"Error forwarding message: {str(e)}")
            logger.info('451 Temporary local problem')

        return b'250 Message accepted for delivery'

def batch_forwarder(cache, lock, webhook_url):
    while True:
        time.sleep(300)  # 5分钟
        with lock:
            if not cache:
                continue
            # 合并所有邮件
            content = ""
            for mail in cache:
                content += (
                    f"from {mail['sender']} \nto {', '.join(mail['recipients'])} "
                    f"\nsubject: {mail['subject']}\n\n{mail['body']}\n"
                    f"{'-'*40}\n"
                )
            cache.clear()
        # 发送到 webhook
        try:
            response = requests.post(
                webhook_url,
                json={
                    "msgtype": "text",
                    "text": {
                        "content": content
                    },
                },
                timeout=10
            )
            if response.status_code == 200:
                logger.info('200 批量Webhook通知已发送')
            else:
                logger.info('550 批量Webhook通知失败')
        except Exception as e:
            logger.error(f"批量转发出错: {str(e)}")

def run_smtp_server():
    SMTP_HOST = get_local_ip()
    # SMTP_PORT = 25252
    logger.info(f"本地局域网IP地址: {SMTP_HOST}")
    logger.info(f"Starting SMTP server on {SMTP_HOST}:{SMTP_PORT}")
    logger.info(f"Webhook target: {WEBHOOK_URL}")

    cache = []
    lock = threading.Lock()

    # 启动批量转发线程
    t = threading.Thread(target=batch_forwarder, args=(cache, lock, WEBHOOK_URL), daemon=True)
    t.start()

    controller = Controller(
        WebhookForwarder(WEBHOOK_URL, cache, lock),
        hostname=SMTP_HOST,
        port=SMTP_PORT
    )
    controller.start()
    try:
        while True:
            time.sleep(600)  # Keep the server running
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Shutting down server...")
        controller.stop()



def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 连接到一个外部地址，不会真的发送数据
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


if __name__ == "__main__":
    run_smtp_server()