from fastapi import FastAPI, APIRouter
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api import config, playlist, plex, importer


app = FastAPI(
    title="Plexlist API",
    description="API for managing and importing playlists to Plex.",
    version="1.0.0",
)

# API Routers
api_router = APIRouter()
api_router.include_router(config.router)
api_router.include_router(playlist.router)
api_router.include_router(plex.router)
api_router.include_router(importer.router)

app.include_router(api_router, prefix="/api/v1")

# Static files for frontend
app.mount("/static", StaticFiles(directory="web/static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('web/index.html')