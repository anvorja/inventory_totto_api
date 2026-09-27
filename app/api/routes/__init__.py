from fastapi import APIRouter

from app.api.routes import auth, catalog, imports, sessions, snapshots, stores, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(stores.router)
api_router.include_router(imports.router)
api_router.include_router(snapshots.router)
api_router.include_router(catalog.router)
api_router.include_router(sessions.router)
