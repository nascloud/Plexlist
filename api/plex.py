from fastapi import APIRouter, HTTPException, BackgroundTasks, status
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uuid
import threading
import sys
import os

# 将项目根目录添加到 sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logic

router = APIRouter(
    tags=["Plex"],
)

# 任务存储 (内存)
tasks: Dict[str, Dict[str, Any]] = {}

# Pydantic 模型
class Song(BaseModel):
    title: str
    artist: str

class ImportOptions(BaseModel):
    mode: str
    playlist_name: Optional[str] = None

class SourceInfo(BaseModel):
    platform_name: str
    original_playlist_title: str

class PlexImportRequest(BaseModel):
    import_options: ImportOptions
    source_info: SourceInfo
    songs: List[Song]

class TaskCreationResponse(BaseModel):
    task_id: str
    message: str

class TaskStatusResult(BaseModel):
    success: bool
    message: str
    final_playlist_name: str
    unmatched_songs: List[Song]

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: Optional[str] = None
    result: Optional[TaskStatusResult] = None
    error: Optional[str] = None

# 任务回调函数
def update_task_progress(task_id: str, progress_message: str):
    tasks[task_id]["status"] = "processing"
    tasks[task_id]["progress"] = progress_message

def complete_task(task_id: str, success: bool, message: str, unmatched: List, final_playlist_name: str):
    if success:
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["result"] = {
            "success": True,
            "message": message,
            "final_playlist_name": final_playlist_name,
            "unmatched_songs": [{"title": t, "artist": a} for t, a in unmatched]
        }
    else:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = message

def plex_import_runner(task_id: str, request: PlexImportRequest):
    """
    实际执行 Plex 导入的包装函数。
    """
    config = logic.load_plex_config()
    plex_url = config.get("plex_url")
    plex_token = config.get("plex_token")

    if not plex_url or not plex_token:
        complete_task(task_id, False, "Plex 配置不完整，请先在配置页面设置。", [], "")
        return

    songs_to_import = [(s.title, s.artist) for s in request.songs]

    logic._import_to_plex_worker(
        plex_url=plex_url,
        plex_token=plex_token,
        plex_playlist_name_input=request.import_options.playlist_name or request.source_info.original_playlist_title,
        songs_to_import=songs_to_import,
        import_mode=request.import_options.mode,
        source_platform_name=request.source_info.platform_name,
        original_playlist_title_hint=request.source_info.original_playlist_title,
        progress_callback=lambda msg: update_task_progress(task_id, msg),
        completion_callback=lambda success, msg, unmatched, final_name: complete_task(task_id, success, msg, unmatched, final_name)
    )

@router.post("/plex/import", response_model=TaskCreationResponse, status_code=status.HTTP_202_ACCEPTED)
def start_plex_import(request: PlexImportRequest, background_tasks: BackgroundTasks):
    """
    启动一个后台任务，将指定的歌曲列表导入到 Plex。
    """
    if not request.songs:
        raise HTTPException(status_code=400, detail="请求数据验证失败（例如，歌曲列表为空）。")

    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "pending", "progress": "任务已创建，等待开始..."}
    
    # 使用 FastAPI 的 BackgroundTasks 来运行后台线程
    background_tasks.add_task(plex_import_runner, task_id, request)

    return {"task_id": task_id, "message": "Plex 导入任务已开始。"}

@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str):
    """
    根据任务ID查询 Plex 导入任务的当前状态、进度和最终结果。
    """
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务ID不存在。")

    response_data = task.copy()
    response_data["task_id"] = task_id
    return response_data