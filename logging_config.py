# logging_config.py
import logging
import logging.handlers
import os
from queue import Queue
import sys
import threading

# 1. 日志队列，用于 GUI 和其他线程通信
log_queue = Queue()

class QueueHandler(logging.Handler):
    """将日志记录发送到队列的 Handler"""
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        self.queue.put(record) # 直接发送 LogRecord 对象，GUI端将负责格式化

def setup_logging():
    """配置根 logger"""
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, 'app.log')

    # 2. 定义日志格式
    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) # 设置根 logger 的级别为 DEBUG

    # 清除已有handler，避免重复添加
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # 3. 控制台 Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO) # 控制台只显示 INFO 及以上级别
    console_handler.setFormatter(log_format)

    # 4. 文件 Handler (每天轮换)
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file, when='midnight', interval=1, backupCount=7, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG) # 文件记录所有 DEBUG 及以上级别
    file_handler.setFormatter(log_format)

    # 5. GUI 队列 Handler
    queue_handler = QueueHandler(log_queue)
    queue_handler.setLevel(logging.INFO) # GUI 只显示 INFO 及以上级别
    # QueueHandler 不需要 formatter，因为我们将在GUI端格式化
    # queue_handler.setFormatter(log_format)

    # 6. 为根 logger 添加 Handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(queue_handler)

def handle_exception(exc_type, exc_value, exc_traceback):
    """全局异常钩子函数"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.getLogger().critical(
        "未捕获的异常", exc_info=(exc_type, exc_value, exc_traceback)
    )

def setup_exception_handling():
    """设置全局异常处理"""
    sys.excepthook = handle_exception
    # 对于 Python 3.8+
    if hasattr(threading, 'excepthook'):
        threading.excepthook = lambda args: handle_exception(args.exc_type, args.exc_value, args.exc_traceback)