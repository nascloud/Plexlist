# 应用程序日志记录功能改进计划

## 1. 概述

当前应用程序的日志记录功能较为初级，后端 (`logic.py`) 使用 `print()` 语句，前端 (`gui.py`) 使用 `messagebox` 和状态栏。这导致日志信息分散、格式不一，且不利于问题排查和持久化。

本计划旨在引入 Python 标准的 `logging` 模块，建立一个统一、健壮且可扩展的日志系统。

**核心目标:**
*   **标准化**: 在整个应用中统一使用 `logging` 模块。
*   **结构化**: 定义统一的日志格式，包含时间戳、级别、模块和消息。
*   **持久化**: 将日志记录到可轮换的文件中。
*   **可视化**: 在 GUI 中实时、清晰地展示日志信息。
*   **健壮性**: 确保所有未处理的异常都能被捕获和记录。

## 2. 整体架构

新的日志系统将通过一个中央配置文件 (`logging_config.py`) 进行初始化。日志记录将流向三个主要目标：控制台、日志文件和一个专用于 GUI 更新的队列。

```mermaid
graph TD
    subgraph Application
        A[logic.py] --> L{logging.getLogger};
        B[gui.py] --> L;
    end

    subgraph Logging System
        L --> H1[Console Handler];
        L --> H2[Rotating File Handler];
        L --> H3[GUI Queue Handler];
    end

    subgraph Outputs
        H1 --> C[控制台];
        H2 --> F[logs/app.log];
        H3 --> Q[日志队列 (Queue)];
    end

    subgraph GUI
        Q --> P[GUI 日志轮询];
        P --> T[日志显示控件 (tk.Text)];
    end
```

## 3. 实施步骤

### 步骤 1: 创建中央日志配置文件 (`logging_config.py`)

创建一个新文件 `logging_config.py`，用于集中管理所有日志配置。

```python
# logging_config.py
import logging
import logging.handlers
import os
from queue import Queue
import sys

# 1. 日志队列，用于 GUI 和其他线程通信
log_queue = Queue()

class QueueHandler(logging.Handler):
    """将日志记录发送到队列的 Handler"""
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        self.queue.put(record)

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
    queue_handler.setFormatter(log_format)

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

```

### 步骤 2: 改造后端 (`logic.py`)

将 `logic.py` 中的 `print()` 语句替换为 `logging` 调用。

**修改示例:**

```python
# logic.py

import logging
# ... 其他导入

logger = logging.getLogger(__name__)

# ...

# 原代码:
# print(f"Warning: 请求歌曲详情失败 (batch starting at {i}): {e}")
# 修改后:
logger.warning(f"请求歌曲详情失败 (batch starting at {i}): {e}")


# 原代码:
# print(f"在Plex中搜索音轨时出错 '{song_name} - {artist_name}': {e}")
# 修改后:
logger.error(f"在Plex中搜索音轨时出错 '{song_name} - {artist_name}'", exc_info=True)

# 原代码:
# print(f"  Plex中未找到: {song_name} - {artist_name}")
# 修改后:
logger.info(f"Plex中未找到: {song_name} - {artist_name}")
```

### 步骤 3: 改造前端 (`gui.py`)

集成日志系统，添加日志显示面板，并统一错误处理。

**主要修改点:**

1.  **导入和初始化**:
    ```python
    # gui.py
    import logging
    import logging_config
    from logging_config import log_queue

    # 在 main 函数或脚本开始处
    logging_config.setup_logging()
    logging_config.setup_exception_handling() # 设置全局异常钩子
    logger = logging.getLogger(__name__)
    ```

2.  **添加日志面板**:
    *   在 `main_paned_window` 中添加一个新的 `ttk.LabelFrame` 作为日志面板。
    *   内部包含一个带滚动条的 `tk.Text` 控件，设置为只读。

3.  **实现日志轮询和显示**:
    ```python
    # gui.py

    class LogViewer(ttk.Frame):
        def __init__(self, parent, *args, **kwargs):
            super().__init__(parent, *args, **kwargs)
            # ... 创建 Text 和 Scrollbar ...
            self.log_text = tk.Text(...)
            self.log_text.config(state=tk.DISABLED)

            # 定义颜色标签
            self.log_text.tag_config('INFO', foreground='black')
            self.log_text.tag_config('DEBUG', foreground='gray')
            self.log_text.tag_config('WARNING', foreground='orange')
            self.log_text.tag_config('ERROR', foreground='red', font=('Helvetica', '9', 'bold'))
            self.log_text.tag_config('CRITICAL', foreground='red', background='yellow', font=('Helvetica', '9', 'bold'))

        def add_log_message(self, record):
            msg = self.log_text.handler.formatter.format(record)
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + '\n', record.levelname)
            self.log_text.config(state=tk.DISABLED)
            self.log_text.yview(tk.END)

    def poll_log_queue(log_viewer_widget):
        while True:
            try:
                record = log_queue.get(block=False)
                log_viewer_widget.add_log_message(record)
            except queue.Empty:
                break
        # 每 100ms 检查一次
        root.after(100, poll_log_queue, log_viewer_widget)

    # 在 GUI 初始化后启动轮询
    # log_viewer = LogViewer(...)
    # poll_log_queue(log_viewer)
    ```

4.  **统一错误处理**:
    *   将 `messagebox.showerror` 的调用与 `logging.error` 结合。
    *   在所有 `try...except` 块中，添加 `logging` 调用。

    **修改示例:**
    ```python
    # gui.py
    # ...
    except requests.exceptions.ConnectionError as e:
        error_msg = f"无法连接到服务器: {e}"
        logger.error(error_msg, exc_info=True) # 记录详细错误
        root.after(0, lambda: messagebox.showerror("网络错误", error_msg))
        root.after(0, lambda: update_status_bar("提取失败：网络连接错误"))
    ```

## 4. 总结

该计划通过引入标准的 `logging` 模块，将应用的日志系统提升到一个新的水平。实施后，开发者将拥有强大的调试工具（控制台和文件日志），而用户也能通过 GUI 中的实时日志获得更清晰的操作反馈。统一的异常处理将确保应用的健壮性，使得问题排查变得更加高效。