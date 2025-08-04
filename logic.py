import json
import requests
import threading
import re
import os
import time
import logging

logger = logging.getLogger(__name__)

try:
    from thefuzz import fuzz
except ImportError:
    fuzz = None

try:
    from plexapi.server import PlexServer
    from plexapi.exceptions import NotFound, Unauthorized
except ImportError:
    PlexServer = None
    NotFound = None
    Unauthorized = None

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
            logger.warning(f"请求歌曲详情失败 (batch starting at {i}): {e}")
            continue
        except json.JSONDecodeError:
            logger.warning(f"解析歌曲详情响应失败 (batch starting at {i})。")
            continue

        if 'songs' in songs_batch_data:
            for track_detail in songs_batch_data['songs']:
                name = track_detail.get('name', '未知歌名')
                artists = ", ".join([artist.get('name', '未知歌手') for artist in track_detail.get('ar', [])])
                all_songs_output.append((name, artists))
        else:
            logger.warning(f"Batch for song details (starting index {i}) did not return 'songs' key.")
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

def extract_playlist_id(url_or_id):
    match = re.search(r'id=(\d+)', url_or_id)
    if match:
        return match.group(1)
    elif url_or_id.isdigit():
        return url_or_id
    else:
        return None

def normalize_string(text):
    """标准化字符串，用于模糊比较。"""
    if not text:
        return ""
    # 转换为小写
    text = text.lower()
    # 移除常见的多余词语和符号
    text = re.sub(r"[\(\[].*?[\)\]]", "", text) # 移除括号和括号内的内容
    text = re.sub(r"deluxe|explicit|remastered|feat\.|ft\.", "", text)
    # 移除所有非字母和数字的字符
    text = re.sub(r'[^\w\s]', '', text)
    return text.strip()

def find_plex_track(plex, song_name, artist_name):
    """
    在Plex中查找音轨，采用多策略匹配：
    1. 精确匹配：尝试直接用歌曲名和艺术家名搜索。
    2. 艺术家内模糊匹配：先找到艺术家，再在其所有歌曲中模糊匹配歌名。
    3. 全局模糊匹配：如果找不到艺术家，则在全局搜索歌名，再对结果进行模糊匹配。
    """
    if fuzz is None:
        logger.warning("'thefuzz' 库未安装，无法进行模糊匹配。请执行 'pip install thefuzz python-Levenshtein'")
        return None

    # 标准化输入
    norm_song_name = normalize_string(song_name)
    norm_artist_name = normalize_string(artist_name)

    try:
        # --- 策略1：精确搜索 (最快) ---
        if artist_name:
            results = plex.library.search(song_name, libtype='track', artist=artist_name)
            if results:
                return results[0]

        # --- 策略2：在艺术家内进行模糊匹配 (推荐) ---
        if norm_artist_name:
            artists = plex.library.search(norm_artist_name, libtype='artist')
            if artists:
                best_match = None
                highest_score = 0
                for artist in artists:
                    for track in artist.tracks():
                        plex_norm_title = normalize_string(track.title)
                        score = fuzz.partial_ratio(norm_song_name, plex_norm_title)
                      
                        if score > highest_score:
                            highest_score = score
                            best_match = track

                if highest_score > 85:
                    logger.info(f"模糊匹配成功 (艺术家内): '{song_name}' -> '{best_match.title}' (相似度: {highest_score})")
                    return best_match

        # --- 策略3：全局模糊搜索 (备用，较慢) ---
        results = plex.library.search(song_name, libtype='track')
        if results:
            best_match = None
            highest_score = 0
            for track in results:
                plex_norm_title = normalize_string(track.title)
                plex_norm_artist = normalize_string(track.artist().title if track.artist() else "")
              
                title_score = fuzz.partial_ratio(norm_song_name, plex_norm_title)
                artist_score = 100 if not norm_artist_name else fuzz.ratio(norm_artist_name, plex_norm_artist)
              
                combined_score = (title_score * 0.7) + (artist_score * 0.3)

                if combined_score > highest_score:
                    highest_score = combined_score
                    best_match = track
          
            if highest_score > 90:
                logger.info(f"模糊匹配成功 (全局): '{song_name}' -> '{best_match.title}' (综合分: {highest_score:.0f})")
                return best_match

    except Exception as e:
        logger.error(f"在Plex中搜索音轨时出错 '{song_name} - {artist_name}'", exc_info=True)
  
    return None

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
                logger.info(f"Plex中未找到: {song_name} - {artist_name}")
        
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