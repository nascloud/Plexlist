import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
import re
import json
import threading
import os
import time
import logic
import logging
import logging_config
from logging_config import log_queue
from queue import Empty

# 在 main 函数或脚本开始处
logging_config.setup_logging()
logging_config.setup_exception_handling() # 设置全局异常钩子
logger = logging.getLogger(__name__)

try:
    from plexapi.server import PlexServer
    from plexapi.exceptions import NotFound, Unauthorized
except ImportError:
    PlexServer = None
    NotFound = None
    Unauthorized = None


# ------------- GUI Event Handlers (Modified and New) -------------
# ... (current_extracted_playlist_title 定义在 root 创建后) ...
# ... (on_extract, on_delete_selected, on_clear 函数不变) ...
def on_extract():
    song_listbox.delete(0, tk.END)
    current_playlist.clear()
    current_extracted_playlist_title.set("未知歌单") # 重置
    update_status_bar("")

    source = source_var.get()
    input_text = playlist_entry.get()
    playlist_id = logic.extract_playlist_id(input_text)
    if not playlist_id:
        logger.error("无法识别歌单ID或链接")
        messagebox.showerror("错误", "无法识别歌单ID或链接")
        return

    extract_button.config(state=tk.DISABLED)
    update_status_bar(f"正在从 {source} 提取歌单ID: {playlist_id}...")

    def extraction_task():
        songs = []
        playlist_title_from_fetch = "未知歌单"
        try:
            if source == "网易云音乐":
                songs, playlist_title_from_fetch = logic.fetch_netease_playlist(playlist_id)
            else:
                songs, playlist_title_from_fetch = logic.fetch_qq_playlist(playlist_id)

            def update_gui_with_songs():
                current_extracted_playlist_title.set(playlist_title_from_fetch) # 保存歌单标题
                if not songs:
                    messagebox.showinfo("提示", "歌单为空或未能获取到歌曲。")
                    update_status_bar("提取完成：歌单为空或未能获取到歌曲。")
                else:
                    for name, artist in songs:
                        song_listbox.insert(tk.END, f"{name} - {artist}")
                        current_playlist.append((name, artist))
                    msg = f"成功提取歌单 '{playlist_title_from_fetch}' ({len(songs)} 首歌曲)！"
                    messagebox.showinfo("完成", msg)
                    update_status_bar(f"提取完成：{msg}")
                extract_button.config(state=tk.NORMAL)
            root.after(0, update_gui_with_songs)
        except ValueError as e:
            logger.error(f"获取歌单失败：{e}", exc_info=True)
            root.after(0, lambda: messagebox.showerror("错误", f"获取歌单失败：{e}"))
            root.after(0, lambda: update_status_bar(f"提取失败：{e}"))
        except requests.exceptions.ConnectionError as e:
            error_msg = f"无法连接到服务器: {e}"
            logger.error(error_msg, exc_info=True)
            root.after(0, lambda: messagebox.showerror("网络错误", error_msg))
            root.after(0, lambda: update_status_bar(f"提取失败：网络连接错误"))
        except requests.exceptions.Timeout:
            logger.error("请求超时", exc_info=True)
            root.after(0, lambda: messagebox.showerror("网络错误", "请求超时，请检查网络连接或稍后再试。"))
            root.after(0, lambda: update_status_bar(f"提取失败：请求超时"))
        except Exception as e:
            logger.critical(f"发生未知错误：{e}", exc_info=True)
            root.after(0, lambda: messagebox.showerror("未知错误", f"发生未知错误：{e}"))
            root.after(0, lambda: update_status_bar(f"提取失败：{e}"))
        finally:
            root.after(0, lambda: extract_button.config(state=tk.NORMAL))
    threading.Thread(target=extraction_task, daemon=True).start()

def on_delete_selected():
    selected_indices = song_listbox.curselection()
    if not selected_indices:
        messagebox.showinfo("提示", "请先选择要删除的歌曲。")
        return
    for index in reversed(selected_indices):
        song_listbox.delete(index)
        del current_playlist[index]
    update_status_bar(f"删除了 {len(selected_indices)} 首歌曲。")


def on_clear():
    song_listbox.delete(0, tk.END)
    current_playlist.clear()
    current_extracted_playlist_title.set("未知歌单")
    messagebox.showinfo("提示", "歌单已清空。")
    update_status_bar("歌单已清空。")

# 新增函数：显示未匹配的歌曲
def show_unmatched_songs_window(unmatched_list):
    if not unmatched_list:
        return # 如果列表为空，则不显示窗口

    unmatched_window = tk.Toplevel(root)
    unmatched_window.title("Plex中未匹配到的歌曲")
    unmatched_window.geometry("500x400")
    unmatched_window.grab_set() # 模态化，阻止与其他窗口交互直到关闭

    label = ttk.Label(unmatched_window, text=f"以下 {len(unmatched_list)} 首歌曲未能自动匹配到Plex库中：")
    label.pack(pady=10)

    text_frame = ttk.Frame(unmatched_window)
    text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))

    unmatched_text = tk.Text(text_frame, wrap=tk.WORD, height=15, width=60)
    unmatched_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=unmatched_text.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    unmatched_text.configure(yscrollcommand=scrollbar.set)

    for song_name, artist_name in unmatched_list:
        unmatched_text.insert(tk.END, f"{song_name} - {artist_name}\n")
    
    unmatched_text.config(state=tk.DISABLED) # 设置为只读

    close_button = ttk.Button(unmatched_window, text="关闭", command=unmatched_window.destroy)
    close_button.pack(pady=10)

    unmatched_window.transient(root) # 设置为 root 的子窗口
    unmatched_window.focus_set() # 设置焦点


def on_import_to_plex():
    if PlexServer is None:
        logger.error("PlexAPI库未安装。")
        messagebox.showerror("错误", "PlexAPI库未安装。\n请在命令行执行: pip install plexapi")
        return

    if not current_playlist:
        logger.warning("试图导入空歌单。")
        messagebox.showinfo("提示", "当前歌单为空，请先提取歌曲。")
        return

    # ... (获取 plex_url, plex_token,等不变) ...
    plex_url = plex_url_entry.get()
    plex_token = plex_token_entry.get()
    plex_playlist_name_str = plex_playlist_name_entry.get()
    import_mode_val = plex_import_mode_var.get()

    if not all([plex_url, plex_token]):
        logger.error("Plex服务器URL或Token为空。")
        messagebox.showerror("错误", "请输入Plex服务器URL和Token。")
        return
    if import_mode_val == "update_existing" and not plex_playlist_name_str:
        logger.error("更新模式下Plex播放列表名称为空。")
        messagebox.showerror("错误", "选择“更新/覆盖现有”模式时，请输入Plex播放列表名称。")
        return

    logic.save_plex_config({
        "plex_url": plex_url,
        "plex_token": plex_token,
        "plex_playlist_name": plex_playlist_name_str,
        "plex_import_mode": import_mode_val
    })
    import_plex_button.config(state=tk.DISABLED)
    
    def progress_callback(message):
        root.after(0, lambda: update_status_bar(message))

    # 修改 completion_callback 以接收 unmatched_songs
    def completion_callback(success, message, unmatched_songs):
        root.after(0, lambda: import_plex_button.config(state=tk.NORMAL))
        root.after(0, lambda: update_status_bar(message))
        if success:
            root.after(0, lambda: messagebox.showinfo("Plex导入", message))
            if unmatched_songs: # 如果有未匹配的歌曲
                root.after(100, lambda: show_unmatched_songs_window(unmatched_songs)) # 稍作延迟显示
        else:
            root.after(0, lambda: messagebox.showerror("Plex导入失败", message))
            # 即使失败，也可能有一些未匹配的记录（比如连接成功但部分匹配失败）
            if unmatched_songs:
                 root.after(100, lambda: show_unmatched_songs_window(unmatched_songs))


    songs_to_import_copy = list(current_playlist)
    source_platform = source_var.get()
    original_title_hint = current_extracted_playlist_title.get()

    thread = threading.Thread(target=logic._import_to_plex_worker,
                              args=(plex_url, plex_token, plex_playlist_name_str,
                                    songs_to_import_copy, import_mode_val,
                                    source_platform, original_title_hint,
                                    progress_callback, completion_callback), # completion_callback现在会接收unmatched_songs
                              daemon=True)
    thread.start()

def update_status_bar(text):
    status_var.set(text)
    logger.info(f"状态更新: {text}")
    root.update_idletasks()

# ------------- GUI 界面布局 -------------

class LogViewer(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.log_text = tk.Text(self, wrap=tk.WORD, height=8, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        # 定义颜色标签
        self.log_text.tag_config('INFO', foreground='black')
        self.log_text.tag_config('DEBUG', foreground='gray')
        self.log_text.tag_config('WARNING', foreground='orange')
        self.log_text.tag_config('ERROR', foreground='red', font=('Helvetica', '9', 'bold'))
        self.log_text.tag_config('CRITICAL', foreground='red', background='yellow', font=('Helvetica', '9', 'bold'))

    def add_log_message(self, record):
        # 从 record 中提取级别和消息
        level = record.levelname
        msg = record.getMessage()
        # 格式化最终消息
        formatted_msg = f"{record.asctime} - {record.name} - {level} - {msg}\n"

        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, formatted_msg, record.levelname)
        self.log_text.config(state=tk.DISABLED)
        self.log_text.yview(tk.END)

def poll_log_queue(log_viewer_widget):
    while True:
        try:
            record = log_queue.get(block=False)
            log_viewer_widget.add_log_message(record)
        except Empty:
            break
    # 每 100ms 检查一次
    root.after(100, poll_log_queue, log_viewer_widget)


root = tk.Tk()
root.title("网易云 / QQ音乐 歌单提取及Plex导入工具")

current_extracted_playlist_title = tk.StringVar(value="未知歌单")
status_var = tk.StringVar()

plex_cfg = logic.load_plex_config()
current_playlist = []

main_paned_window = ttk.PanedWindow(root, orient=tk.VERTICAL)
main_paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

# ... (extraction_frame_container, song_list_main_frame, plex_frame_container 不变) ...
extraction_frame_container = ttk.Frame(main_paned_window, padding=5)
main_paned_window.add(extraction_frame_container, weight=0)
extraction_frame_container.grid_columnconfigure(1, weight=1)
ttk.Label(extraction_frame_container, text="歌单来源：").grid(row=0, column=0, padx=(0,5), pady=5, sticky="w")
source_var = tk.StringVar(value="网易云音乐")
source_dropdown = ttk.Combobox(extraction_frame_container, textvariable=source_var, values=["网易云音乐", "QQ音乐"], state="readonly", width=15)
source_dropdown.grid(row=0, column=1, pady=5, sticky="w")
ttk.Label(extraction_frame_container, text="歌单ID/链接：").grid(row=1, column=0, padx=(0,5), pady=5, sticky="w")
playlist_entry = ttk.Entry(extraction_frame_container)
playlist_entry.grid(row=1, column=1, pady=5, sticky="ew")
extract_button = ttk.Button(extraction_frame_container, text="提取歌单", command=on_extract)
extract_button.grid(row=2, column=0, columnspan=2, pady=10, sticky="ew")

song_list_main_frame = ttk.Frame(main_paned_window, padding=5)
main_paned_window.add(song_list_main_frame, weight=1)
song_list_main_frame.grid_rowconfigure(0, weight=1)
song_list_main_frame.grid_columnconfigure(0, weight=1)
list_frame = ttk.Frame(song_list_main_frame)
list_frame.grid(row=0, column=0, sticky="nsew", pady=(0,5))
list_frame.grid_rowconfigure(0, weight=1)
list_frame.grid_columnconfigure(0, weight=1)
song_listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, width=70, height=15)
song_listbox.grid(row=0, column=0, sticky="nsew")
scrollbar_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=song_listbox.yview)
scrollbar_y.grid(row=0, column=1, sticky="ns")
song_listbox.configure(yscrollcommand=scrollbar_y.set)
scrollbar_x = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=song_listbox.xview)
scrollbar_x.grid(row=1, column=0, sticky="ew")
song_listbox.configure(xscrollcommand=scrollbar_x.set)
list_btn_frame = ttk.Frame(song_list_main_frame)
list_btn_frame.grid(row=1, column=0, sticky="ew")
list_btn_frame.grid_columnconfigure(0, weight=1)
list_btn_frame.grid_columnconfigure(1, weight=1)
ttk.Button(list_btn_frame, text="删除选中", command=on_delete_selected).pack(side=tk.LEFT, padx=5, expand=True)
ttk.Button(list_btn_frame, text="清空歌单", command=on_clear).pack(side=tk.LEFT, padx=5, expand=True)

plex_frame_container = ttk.LabelFrame(main_paned_window, text="Plex导入设置", padding=10)
main_paned_window.add(plex_frame_container, weight=0)
plex_frame_container.grid_columnconfigure(1, weight=1)
plex_import_mode_var = tk.StringVar(value=plex_cfg.get("plex_import_mode", "create_new"))
mode_frame = ttk.Frame(plex_frame_container)
mode_frame.grid(row=0, column=0, columnspan=2, pady=2, sticky="w")
ttk.Label(mode_frame, text="导入模式:").pack(side=tk.LEFT, padx=(0,5))
ttk.Radiobutton(mode_frame, text="创建新歌单", variable=plex_import_mode_var, value="create_new").pack(side=tk.LEFT)
ttk.Radiobutton(mode_frame, text="更新/覆盖现有", variable=plex_import_mode_var, value="update_existing").pack(side=tk.LEFT, padx=(10,0))
ttk.Label(plex_frame_container, text="Plex 服务器URL:").grid(row=1, column=0, padx=5, pady=2, sticky="w")
plex_url_entry = ttk.Entry(plex_frame_container, width=40)
plex_url_entry.grid(row=1, column=1, padx=5, pady=2, sticky="ew")
plex_url_entry.insert(0, plex_cfg.get("plex_url", "http://localhost:32400"))
ttk.Label(plex_frame_container, text="Plex Token:").grid(row=2, column=0, padx=5, pady=2, sticky="w")
plex_token_entry = ttk.Entry(plex_frame_container, width=40, show="*")
plex_token_entry.grid(row=2, column=1, padx=5, pady=2, sticky="ew")
plex_token_entry.insert(0, plex_cfg.get("plex_token", ""))
ttk.Label(plex_frame_container, text="Plex 播放列表名:").grid(row=3, column=0, padx=5, pady=2, sticky="w")
plex_playlist_name_entry = ttk.Entry(plex_frame_container, width=40)
plex_playlist_name_entry.grid(row=3, column=1, padx=5, pady=2, sticky="ew")
plex_playlist_name_entry.insert(0, plex_cfg.get("plex_playlist_name", "导入的歌单"))
ttk.Label(plex_frame_container, text="(“更新/覆盖”模式下使用此名称；“创建新的”模式下会自动生成名称)").grid(row=4, column=1, padx=5, pady=(0,5), sticky="w", columnspan=1)
import_plex_button = ttk.Button(plex_frame_container, text="导入到Plex", command=on_import_to_plex)
import_plex_button.grid(row=5, column=0, columnspan=2, pady=10, sticky="ew")

# 添加日志查看器
log_frame = ttk.LabelFrame(main_paned_window, text="日志", padding=5)
main_paned_window.add(log_frame, weight=0) # weight=0 表示初始高度较小
log_viewer = LogViewer(log_frame)
log_viewer.pack(fill=tk.BOTH, expand=True)

status_bar = ttk.Label(root, textvariable=status_var, relief=tk.SUNKEN, anchor=tk.W, padding=2)
status_bar.pack(side=tk.BOTTOM, fill=tk.X)
update_status_bar("就绪。")

# 启动日志队列轮询
poll_log_queue(log_viewer)

root.minsize(550, 750) # 增加最小高度以容纳日志面板
root.mainloop()