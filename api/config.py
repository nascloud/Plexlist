from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import sys
import os

# 将项目根目录添加到 sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logic

router = APIRouter(
    prefix="/config",
    tags=["Config"],
)

# Pydantic 模型
from typing import Optional

class PlexConfig(BaseModel):
    plex_url: Optional[str] = Field(None, description="Plex Server URL")
    plex_token: Optional[str] = Field(None, description="Plex Server Token")
    plex_playlist_name: Optional[str] = Field(None, description="Default playlist name for Plex import")
    plex_import_mode: Optional[str] = Field(None, description="Import mode ('create_new' or 'update_existing')")

class SaveConfigResponse(BaseModel):
    message: str

@router.get("/plex", response_model=PlexConfig)
def get_plex_config():
    """
    获取保存在服务器上的 Plex 配置信息。
    """
    try:
        config = logic.load_plex_config()
        # 为可能缺失的键提供默认值，以确保响应模型验证通过
        return PlexConfig(
            plex_url=config.get("plex_url", ""),
            plex_token=config.get("plex_token", ""),
            plex_playlist_name=config.get("plex_playlist_name", "导入的歌单"),
            plex_import_mode=config.get("plex_import_mode", "create_new")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="读取配置文件时出错。")

@router.post("/plex", response_model=SaveConfigResponse)
def save_plex_config_api(config_update: PlexConfig):
    """
    保存或更新 Plex 配置信息。允许部分更新。
    """
    try:
        # 加载现有配置
        existing_config = logic.load_plex_config()
        
        # 使用请求中的新数据更新现有配置
        update_data = config_update.dict(exclude_unset=True)
        updated_config = {**existing_config, **update_data}
        
        logic.save_plex_config(updated_config)
        return {"message": "Plex 配置已成功保存。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入配置文件时出错: {e}")