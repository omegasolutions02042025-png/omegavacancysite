"""
WebSocket менеджер для чата
Отдельный модуль для избежания циклических импортов
"""
from fastapi import WebSocket
from typing import Dict, List


class ChatConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        print(f"[CHAT_WS] Пользователь {user_id} подключился. Всего соединений: {len(self.active_connections[user_id])}")

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
                print(f"[CHAT_WS] Пользователь {user_id} отключился. Осталось соединений: {len(self.active_connections[user_id])}")
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, user_id: int):
        """Отправить сообщение конкретному пользователю"""
        if user_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                    print(f"[CHAT_WS] Отправлено сообщение пользователю {user_id}: {message.get('type')}")
                except Exception as e:
                    print(f"[CHAT_WS] Ошибка отправки пользователю {user_id}: {e}")
                    disconnected.append(connection)
            
            # Удаляем отключенные соединения
            for conn in disconnected:
                self.disconnect(conn, user_id)
        else:
            print(f"[CHAT_WS] Нет активных соединений для user_id={user_id}")


# Глобальный экземпляр менеджера
chat_ws_manager = ChatConnectionManager()

