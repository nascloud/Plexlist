import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
import re
import json
import threading
import os
import time

try:
    from plexapi.server import PlexServer
    from plexapi.exceptions import NotFound, Unauthorized
except ImportError:
    PlexServer = None
    NotFound = None
    Unauthorized = None

# ... (PLEX_CONFIG_FILE, load_plex_config, save_plex_config 函数不变) ...
PLEX_CONFIG_FILE = "plex_config.json"
def load_plex_config():
    if os.path.exists(PLEX_CONFIG_FILE):
        try:
            with open(PLEX_CONFIG_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {} # Corrupted file
    return {}

def save_plex_config(config):
    with open(PLEX_CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

# ... (fetch_netease_playlist, fetch_qq_playlist 函数不变，确保它们返回 songs, playlist_title) ...
def fetch_netease_playlist(playlist_id):
    playlist_url = f"https://music.163.com/api/v6/playlist/detail?id={playlist_id}"
    headers_playlist = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://music.163.com/",
        "Cookie": "appver=2.0.2; os=pc;"
    }
    try:
        res_playlist = requests.get(playlist_url, headers=headers_playlist, timeout=10)
        res_playlist.raise_for_status()
        playlist_data = res_playlist.json()
    except requests.exceptions.RequestException as e:
        raise ValueError(f"请求歌单ID列表失败: {e}")
    except json.JSONDecodeError:
        raise ValueError("解析歌单ID列表响应失败，可能不是有效的JSON。")

    playlist_title = "未知歌单"
    if 'playlist' in playlist_data and 'name' in playlist_data['playlist']:
        playlist_title = playlist_data['playlist']['name']

    if 'playlist' not in playlist_data or 'trackIds' not in playlist_data['playlist']:
        if 'playlist' in playlist_data and 'tracks' in playlist_data['playlist']:
            songs_limited = []
            for track in playlist_data['playlist']['tracks']:
                name = track.get('name', '未知歌名')
                artists = ", ".join([a.get('name', '未知歌手') for a in track.get('ar', [])])
                songs_limited.append((name, artists))
            if not songs_limited:
                 raise ValueError("无法获取歌单内容（trackIds 和 tracks 均为空或无效），请确认ID是否正确，或歌单是否为公开。")
            return songs_limited, playlist_title # 返回歌曲和标题
        raise ValueError("无法获取歌单内容（playlist 或 trackIds 键不存在），请确认ID是否正确，或歌单是否为公开。")

    track_ids_info = playlist_data['playlist']['trackIds']
    track_ids = [str(item['id']) for item in track_ids_info]

    if not track_ids:
        if 'tracks' in playlist_data['playlist'] and playlist_data['playlist']['tracks']:
            songs_limited = []
            for track in playlist_data['playlist']['tracks']:
                name = track.get('name', '未知歌名')
                artists = ", ".join([a.get('name', '未知歌手') for a in track.get('ar', [])])
                songs_limited.append((name, artists))
            return songs_limited, playlist_title # 返回歌曲和标题
        return [], playlist_title # 返回空歌曲列表和标题

    song_details_url = "https://music.163.com/api/v3/song/detail"
    headers_songs = headers_playlist.copy()
    all_songs_output = []
    batch_size = 500

    for i in range(0, len(track_ids), batch_size):
        current_batch_ids = track_ids[i:i + batch_size]
        c_param_value = json.dumps([{"id": tid} for tid in current_batch_ids])
        payload = {'c': c_param_value}
        try:
            res_songs = requests.post(song_details_url, headers=headers_songs, data=payload, timeout=15)
            res_songs.raise_for_status()
            songs_batch_data = res_songs.json()
        except requests.exceptions.RequestException as e:
            print(f"Warning: 请求歌曲详情失败 (batch starting at {i}): {e}")
            continue
        except json.JSONDecodeError:
            print(f"Warning: 解析歌曲详情响应失败 (batch starting at {i})。")
            continue

        if 'songs' in songs_batch_data:
            for track_detail in songs_batch_data['songs']:
                name = track_detail.get('name', '未知歌名')
                artists = ", ".join([artist.get('name', '未知歌手') for artist in track_detail.get('ar', [])])
                all_songs_output.append((name, artists))
        else:
            print(f"Warning: Batch for song details (starting index {i}) did not return 'songs' key.")
    return all_songs_output, playlist_title # 返回歌曲和标题

def fetch_qq_playlist(playlist_id):
    url = f"https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg"
    params = {
        'type': '1', 'json': '1', 'utf8': '1', 'onlysong': '0',
        'disstid': playlist_id, 'format': 'json', 'platform': 'yqq.json'
    }
    headers = {
        'referer': 'https://y.qq.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
    except requests.exceptions.RequestException as e:
        raise ValueError(f"请求QQ音乐歌单失败: {e}")
    except json.JSONDecodeError:
        raise ValueError("解析QQ音乐歌单响应失败，可能不是有效的JSON。")

    playlist_title = "未知歌单"
    songs = []
    if 'cdlist' not in data or not data['cdlist'] or 'songlist' not in data['cdlist'][0]:
        raise ValueError("QQ音乐歌单格式不正确或歌单为空")

    if 'dissname' in data['cdlist'][0]:
        playlist_title = data['cdlist'][0]['dissname']

    for song_item in data['cdlist'][0]['songlist']:
        name = song_item.get('songname', '未知歌名')
        artists_list = [s.get('name', '未知歌手') for s in song_item.get('singer', [])]
        artist = ", ".join(artists_list) if artists_list else "未知歌手"
        songs.append((name, artist))
    return songs, playlist_title

# ... (extract_playlist_id, find_plex_track 函数不变) ...
def extract_playlist_id(url_or_id):
    match = re.search(r'id=(\d+)', url_or_id)
    if match:
        return match.group(1)
    elif url_or_id.isdigit():
        return url_or_id
    else:
        return None

def find_plex_track(plex, song_name, artist_name):
    norm_song_name = song_name.lower()
    norm_artist_name = ""
    if artist_name and isinstance(artist_name, str):
        norm_artist_name = artist_name.lower().split(',')[0].strip()
    try:
        for section in plex.library.sections():
            if section.type == 'artist':
                results = section.searchTracks(title=song_name)
                if results:
                    for track in results:
                        plex_track_artists_lower = []
                        if hasattr(track, 'artists') and track.artists:
                            plex_track_artists_lower = [a.title.lower() for a in track.artists if a.title]
                        elif hasattr(track, 'artist') and track.artist() and track.artist().title:
                             plex_track_artists_lower = [track.artist().title.lower()]
                        elif track.grandparentTitle:
                            plex_track_artists_lower = [track.grandparentTitle.lower()]
                        if not norm_artist_name and results: # 艺术家名为空时，标题匹配即可
                            return track
                        if any(norm_artist_name in p_artist for p_artist in plex_track_artists_lower):
                            return track
                        if not plex_track_artists_lower and norm_artist_name and norm_artist_name in track.title.lower():
                            return track
    except Exception as e:
        print(f"Error searching Plex track '{song_name} - {artist_name}': {e}")
    return None

# ------------- Plex Integration Functions (MODIFIED) -------------
def _import_to_plex_worker(plex_url, plex_token, plex_playlist_name_input, songs_to_import,
                           import_mode, source_platform_name, original_playlist_title_hint,
                           progress_callback, completion_callback): # completion_callback会接收unmatched_songs
    """Worker function to run in a separate thread."""
    unmatched_songs_list = [] # <--- 新增：用于存储未匹配的歌曲

    if PlexServer is None:
        # completion_callback(success, message, unmatched_songs)
        completion_callback(False, "PlexAPI库未安装。请先执行 'pip install plexapi'。", [])
        return

    try:
        plex = PlexServer(plex_url, plex_token, timeout=20)
        try:
            plex.clients()
        except Unauthorized:
            completion_callback(False, "Plex授权失败：Token无效或服务器URL不正确。", [])
            return
        except requests.exceptions.ConnectionError:
            completion_callback(False, f"无法连接到Plex服务器：{plex_url}", [])
            return
        except Exception as e:
            completion_callback(False, f"连接Plex时发生错误: {e}", [])
            return

        plex_playlist = None
        target_plex_playlist_name = plex_playlist_name_input

        # ... (创建或更新播放列表的逻辑不变，只是在出错时 completion_callback 要多传一个空列表) ...
        if import_mode == "create_new":
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            base_name = original_playlist_title_hint if original_playlist_title_hint and original_playlist_title_hint != "未知歌单" else "导入歌单"
            target_plex_playlist_name = f"来自{source_platform_name} - {base_name} ({timestamp})"
            progress_callback(f"准备创建新的Plex播放列表：'{target_plex_playlist_name}'")
            try:
                music_sections = [s for s in plex.library.sections() if s.type == 'artist']
                if not music_sections:
                    completion_callback(False, "Plex库中找不到音乐内容，无法创建播放列表。", [])
                    return
                first_track_in_library = music_sections[0].all(libtype='track', maxresults=1)[0]
                plex_playlist = plex.createPlaylist(target_plex_playlist_name, items=[first_track_in_library])
                plex_playlist.removeItems([first_track_in_library])
                progress_callback(f"已创建新的Plex播放列表：'{target_plex_playlist_name}'")
            except IndexError:
                completion_callback(False, "Plex音乐库为空，无法创建播放列表的参照。", [])
                return
            except Exception as e:
                completion_callback(False, f"创建新的Plex播放列表 '{target_plex_playlist_name}' 时出错: {e}", [])
                return
        elif import_mode == "update_existing":
            progress_callback(f"准备更新/覆盖Plex播放列表：'{target_plex_playlist_name}'")
            try:
                plex_playlist = plex.playlist(target_plex_playlist_name)
                if plex_playlist:
                    progress_callback(f"找到现有播放列表 '{target_plex_playlist_name}'，将清空并重新添加。")
                    plex_playlist.removeItems(plex_playlist.items())
                else:
                    progress_callback(f"播放列表 '{target_plex_playlist_name}' 不存在，将创建它。")
                    music_sections = [s for s in plex.library.sections() if s.type == 'artist']
                    if not music_sections:
                        completion_callback(False, "Plex库中找不到音乐内容，无法创建播放列表。", [])
                        return
                    first_track_in_library = music_sections[0].all(libtype='track', maxresults=1)[0]
                    plex_playlist = plex.createPlaylist(target_plex_playlist_name, items=[first_track_in_library])
                    plex_playlist.removeItems([first_track_in_library])
                    progress_callback(f"已创建播放列表：'{target_plex_playlist_name}'")
            except NotFound:
                progress_callback(f"在“更新模式”下，播放列表 '{target_plex_playlist_name}' 未找到，将尝试创建。")
                try:
                    music_sections = [s for s in plex.library.sections() if s.type == 'artist']
                    if not music_sections:
                        completion_callback(False, "Plex库中找不到音乐内容，无法创建播放列表。", [])
                        return
                    first_track_in_library = music_sections[0].all(libtype='track', maxresults=1)[0]
                    plex_playlist = plex.createPlaylist(target_plex_playlist_name, items=[first_track_in_library])
                    plex_playlist.removeItems([first_track_in_library])
                    progress_callback(f"已创建新的Plex播放列表：'{target_plex_playlist_name}'")
                except IndexError:
                    completion_callback(False, "Plex音乐库为空，无法创建播放列表的参照。", [])
                    return
                except Exception as e:
                    completion_callback(False, f"创建播放列表 '{target_plex_playlist_name}' 时出错: {e}", [])
                    return
            except Exception as e:
                completion_callback(False, f"处理Plex播放列表 '{target_plex_playlist_name}' 时出错: {e}", [])
                return
        else:
            completion_callback(False, "无效的Plex导入模式。", [])
            return

        if not plex_playlist:
            completion_callback(False, f"未能为 '{target_plex_playlist_name}' 获取或创建Plex播放列表对象。", [])
            return

        found_count = 0
        not_found_count = 0 # 这个变量可以用来确认 unmatched_songs_list 的长度
        plex_tracks_to_add = []

        for i, (song_name, artist_name) in enumerate(songs_to_import):
            progress_callback(f"正在处理: {i+1}/{len(songs_to_import)} - {song_name} ({target_plex_playlist_name})")
            plex_track = find_plex_track(plex, song_name, artist_name)
            if plex_track:
                plex_tracks_to_add.append(plex_track)
                found_count += 1
            else:
                # not_found_count +=1 # 这个计数器现在由 unmatched_songs_list.append 隐式完成
                unmatched_songs_list.append((song_name, artist_name)) # <--- 收集未匹配的歌曲
                print(f"  Plex中未找到: {song_name} - {artist_name}")
        
        if plex_tracks_to_add:
            progress_callback(f"正在将 {len(plex_tracks_to_add)} 首歌曲添加到Plex播放列表 '{target_plex_playlist_name}'...")
            try:
                plex_playlist.addItems(plex_tracks_to_add)
                progress_callback(f"添加完成。")
            except Exception as e:
                completion_callback(False, f"添加到Plex播放列表 '{target_plex_playlist_name}' 时出错: {e}", unmatched_songs_list)
                return
        
        final_message = (
            f"Plex导入到 '{target_plex_playlist_name}' 完成！\n"
            f"成功匹配并添加: {found_count}首\n"
            f"未在Plex中找到: {len(unmatched_songs_list)}首"
        )
        completion_callback(True, final_message, unmatched_songs_list)

    except Unauthorized:
        completion_callback(False, "Plex授权失败：Token无效或服务器URL不正确。", [])
    except requests.exceptions.ConnectionError:
        completion_callback(False, f"无法连接到Plex服务器：{plex_url}", [])
    except requests.exceptions.Timeout:
        completion_callback(False, "连接Plex服务器超时。", [])
    except Exception as e:
        completion_callback(False, f"Plex导入过程中发生未知错误: {e}", [])


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
    playlist_id = extract_playlist_id(input_text)
    if not playlist_id:
        messagebox.showerror("错误", "无法识别歌单ID或链接")
        return

    extract_button.config(state=tk.DISABLED)
    update_status_bar(f"正在从 {source} 提取歌单ID: {playlist_id}...")

    def extraction_task():
        songs = []
        playlist_title_from_fetch = "未知歌单"
        try:
            if source == "网易云音乐":
                songs, playlist_title_from_fetch = fetch_netease_playlist(playlist_id)
            else:
                songs, playlist_title_from_fetch = fetch_qq_playlist(playlist_id)

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
            root.after(0, lambda: messagebox.showerror("错误", f"获取歌单失败：{e}"))
            root.after(0, lambda: update_status_bar(f"提取失败：{e}"))
        except requests.exceptions.ConnectionError as e:
            root.after(0, lambda: messagebox.showerror("网络错误", f"无法连接到服务器: {e}"))
            root.after(0, lambda: update_status_bar(f"提取失败：网络连接错误"))
        except requests.exceptions.Timeout:
            root.after(0, lambda: messagebox.showerror("网络错误", "请求超时，请检查网络连接或稍后再试。"))
            root.after(0, lambda: update_status_bar(f"提取失败：请求超时"))
        except Exception as e:
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
        messagebox.showerror("错误", "PlexAPI库未安装。\n请在命令行执行: pip install plexapi")
        return

    if not current_playlist:
        messagebox.showinfo("提示", "当前歌单为空，请先提取歌曲。")
        return

    # ... (获取 plex_url, plex_token,等不变) ...
    plex_url = plex_url_entry.get()
    plex_token = plex_token_entry.get()
    plex_playlist_name_str = plex_playlist_name_entry.get()
    import_mode_val = plex_import_mode_var.get()

    if not all([plex_url, plex_token]):
        messagebox.showerror("错误", "请输入Plex服务器URL和Token。")
        return
    if import_mode_val == "update_existing" and not plex_playlist_name_str:
        messagebox.showerror("错误", "选择“更新/覆盖现有”模式时，请输入Plex播放列表名称。")
        return

    save_plex_config({
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

    thread = threading.Thread(target=_import_to_plex_worker,
                              args=(plex_url, plex_token, plex_playlist_name_str,
                                    songs_to_import_copy, import_mode_val,
                                    source_platform, original_title_hint,
                                    progress_callback, completion_callback), # completion_callback现在会接收unmatched_songs
                              daemon=True)
    thread.start()

def update_status_bar(text):
    status_var.set(text)
    root.update_idletasks()

# ------------- GUI 界面布局 -------------
root = tk.Tk()
root.title("网易云 / QQ音乐 歌单提取及Plex导入工具")

current_extracted_playlist_title = tk.StringVar(value="未知歌单")
status_var = tk.StringVar()

plex_cfg = load_plex_config()
current_playlist = []

# ... (GUI布局的其余部分，main_paned_window, extraction_frame_container, song_list_main_frame, plex_frame_container, status_bar 不变) ...
main_paned_window = ttk.PanedWindow(root, orient=tk.VERTICAL)
main_paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
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
ttk.Label(plex_frame_container, text="(“更新/覆盖”模式下使用此名称；“创建新的”模式下会自动生成名称)").grid(row=4, column=1, padx=5, pady=(0,5), sticky="w", columnspan=1) # 修正：columnspan 应为1或2，取决于布局意图
import_plex_button = ttk.Button(plex_frame_container, text="导入到Plex", command=on_import_to_plex)
import_plex_button.grid(row=5, column=0, columnspan=2, pady=10, sticky="ew")
status_bar = ttk.Label(root, textvariable=status_var, relief=tk.SUNKEN, anchor=tk.W, padding=2)
status_bar.pack(side=tk.BOTTOM, fill=tk.X)
update_status_bar("就绪。")

root.minsize(550, 650)
root.mainloop()