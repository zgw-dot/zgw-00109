from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.routers import templates, task_packages, readings, conflicts, audit, reports, batch

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="离线巡检任务包服务",
    description="提供巡检模板管理、任务包生成发放、读数上传、冲突解决、报告导出等功能的本地后端服务",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(templates.router)
app.include_router(task_packages.router)
app.include_router(readings.router)
app.include_router(conflicts.router)
app.include_router(audit.router)
app.include_router(reports.router)
app.include_router(batch.router)


@app.get("/", tags=["系统"])
def root():
    return {
        "name": "离线巡检任务包服务",
        "version": "1.0.0",
        "status": "running",
        "docs": "/api/docs",
        "api_endpoints": [
            "/api/templates",
            "/api/task-packages",
            "/api/readings",
            "/api/conflicts",
            "/api/audit-logs",
            "/api/reports",
            "/api/batch"
        ]
    }


@app.get("/health", tags=["系统"])
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
