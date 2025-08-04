import uuid
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from typing import List, Tuple

from app_state import executor, task_status
from logic import _import_to_plex_worker, extract_playlist_id, fetch_netease_playlist, fetch_qq_playlist

router = APIRouter()

class ImportRequest(BaseModel):
    playlist_url: str
    plex_url: str
    plex_token: str
    plex_playlist_name: str
    import_mode: str # "create_new" or "update_existing"

@router.post("/import", tags=["Importer"])
async def start_import(request: ImportRequest):
    """
    Starts a new playlist import task.
    """
    # 验证导入模式
    if request.import_mode not in ["create_new", "update_existing"]:
        raise HTTPException(
            status_code=400,
            detail=f"无效的导入模式: {request.import_mode}. 只支持 'create_new' 或 'update_existing'"
        )

    task_id = str(uuid.uuid4())
    task_status[task_id] = {"status": "pending", "progress": 0, "total": 0, "message": "任务已排队"}

    playlist_id = extract_playlist_id(request.playlist_url)
    if not playlist_id:
        raise HTTPException(status_code=400, detail="无效的播放列表URL或ID")

    try:
        if "music.163.com" in request.playlist_url:
            songs_to_import, playlist_title = fetch_netease_playlist(playlist_id)
            source_platform = "网易云音乐"
        elif "y.qq.com" in request.playlist_url:
            songs_to_import, playlist_title = fetch_qq_playlist(playlist_id)
            source_platform = "QQ音乐"
        else:
            raise HTTPException(status_code=400, detail="不支持的播放列表URL")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not songs_to_import:
        raise HTTPException(status_code=404, detail="无法从URL获取任何歌曲。")

    # Submit the worker to the thread pool
    executor.submit(
        _import_to_plex_worker,
        plex_url=request.plex_url,
        plex_token=request.plex_token,
        plex_playlist_name_input=request.plex_playlist_name,
        songs_to_import=songs_to_import,
        import_mode=request.import_mode,
        source_platform_name=source_platform,
        original_playlist_title_hint=playlist_title,
        task_id=task_id,
        task_status_dict=task_status
    )

    return {"task_id": task_id}


@router.get("/import/status/{task_id}", tags=["Importer"])
async def get_import_status(task_id: str):
    """
    Retrieves the status of an import task.
    
    Returns:
        {
            "status": "pending|processing|completed|failed|error",
            "message": str,
            "progress": int,
            "total": int,
            "unmatched_songs": list[tuple] (optional)
        }
    """
    status = task_status.get(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="找不到任务ID")
    
    # 确保返回完整的结构
    return {
        "status": status.get("status", "unknown"),
        "message": status.get("message", ""),
        "progress": status.get("progress", 0),
        "total": status.get("total", 0),
        "unmatched_songs": status.get("unmatched_songs", [])
    }