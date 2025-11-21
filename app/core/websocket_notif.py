# app/core/ws_notifications.py
import json
from typing import Dict, List
from fastapi import WebSocket

class WSNotificationManager:
    def __init__(self) -> None:
        # user_id -> список вебсокетов этого пользователя
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        print(f"[ws] user {user_id} connected, total={len(self.active_connections[user_id])}")

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        conns = self.active_connections.get(user_id)
        if not conns:
            return
        try:
            conns.remove(websocket)
        except ValueError:
            pass
        if not conns:
            self.active_connections.pop(user_id, None)
        print(f"[ws] user {user_id} disconnected, left={len(self.active_connections.get(user_id, []))}")

    async def send_to_user(self, user_id: int, data: dict) -> None:
        """
        Шлём одно уведомление всем открытым вкладкам пользователя.
        data — словарь, который на фронте ты парсишь как JSON.
        """
        conns = self.active_connections.get(user_id, [])
        if not conns:
            return
        dead: List[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(data)
            except Exception as e:
                print(f"[ws] error send to {user_id}: {e}")
                dead.append(ws)
        # подчистим оборванные подключения
        for ws in dead:
            try:
                conns.remove(ws)
            except ValueError:
                pass
        if not conns:
            self.active_connections.pop(user_id, None)


ws_manager = WSNotificationManager()
