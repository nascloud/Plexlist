from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List
import sys
import os

# 将项目根目录添加到 sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logic

router = APIRouter(
    prefix="/playlist",
    tags=["Playlist"],
)

# Pydantic 模型
class ExtractRequest(BaseModel):
    source: str = Field(..., description="The source of the playlist, 'netease' or 'qq'")
    url_or_id: str = Field(..., description="The URL or ID of the playlist")

class Song(BaseModel):
    title: str
    artist: str

class ExtractResponse(BaseModel):
    playlist_title: str
    songs: List[Song]

@router.post("/extract", response_model=ExtractResponse)
def extract_playlist(request: ExtractRequest):
    """
    根据提供的歌单来源和 URL/ID，提取歌单的歌曲列表。
    """
    playlist_id = logic.extract_playlist_id(request.url_or_id)
    if not playlist_id:
        raise HTTPException(status_code=400, detail="无法识别的歌单ID或链接。")

    try:
        if request.source == "netease":
            songs_tuple, playlist_title = logic.fetch_netease_playlist(playlist_id)
        elif request.source == "qq":
            songs_tuple, playlist_title = logic.fetch_qq_playlist(playlist_id)
        else:
            raise HTTPException(status_code=400, detail="不支持的歌单来源。")

        songs_list = [{"title": title, "artist": artist} for title, artist in songs_tuple]
        
        if not songs_list:
             raise HTTPException(status_code=404, detail="无法获取歌单内容，请确认ID是否正确，或歌单是否为公开。")

        return {"playlist_title": playlist_title, "songs": songs_list}

    except ValueError as e:
        # 根据错误信息区分404和500
        if "无法获取歌单内容" in str(e) or "格式不正确" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        else:
            raise HTTPException(status_code=500, detail=f"请求音乐平台时发生网络错误或解析错误: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提取歌单时发生未知错误: {e}")