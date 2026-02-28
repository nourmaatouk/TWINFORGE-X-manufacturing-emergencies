"""MCP Mock Server - Main FastAPI entry point."""

from fastapi import FastAPI
from app.config import settings

app = FastAPI(title="MCP Mock Server", version="1.0.0")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "mcp-mock-server"}


@app.get("/tools")
async def list_tools():
    return [
        {"name": "cnc_read_sensors", "description": "Read CNC machine sensors"},
        {"name": "robot_get_position", "description": "Get robot arm position"},
        {"name": "conveyor_get_speed", "description": "Get conveyor belt speed"},
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9001)
