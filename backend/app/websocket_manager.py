# backend/app/websocket_manager.py

from typing import Dict, Set
from fastapi import WebSocket
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # Ключ – dataset_id, значение – множество активных WebSocket-соединений
        self.active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, dataset_id: int):
        await websocket.accept()
        if dataset_id not in self.active_connections:
            self.active_connections[dataset_id] = set()
        self.active_connections[dataset_id].add(websocket)
        logger.info(
            f"WebSocket connected to dataset {dataset_id}, "
            f"total: {len(self.active_connections[dataset_id])}"
        )

    def disconnect(self, websocket: WebSocket, dataset_id: int):
        if dataset_id in self.active_connections:
            self.active_connections[dataset_id].discard(websocket)
            if not self.active_connections[dataset_id]:
                del self.active_connections[dataset_id]
            logger.info(f"WebSocket disconnected from dataset {dataset_id}")

    async def broadcast(self, dataset_id: int, message: dict):
        if dataset_id not in self.active_connections:
            return
        dead = set()
        for connection in self.active_connections[dataset_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"WebSocket send error: {e}")
                dead.add(connection)
        for conn in dead:
            self.active_connections[dataset_id].discard(conn)


manager = ConnectionManager()