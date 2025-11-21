# app/routes/ws_notifications.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.websocket_notif import ws_manager

router = APIRouter()

@router.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket):
    """
    Фронт подключается так:
    ws://host/ws/notifications?user_id=4
    (в проде будет wss://)
    """
    user_q = websocket.query_params.get("user_id")
    if not user_q:
        await websocket.close(code=4401)
        return

    try:
        user_id = int(user_q)
    except ValueError:
        await websocket.close(code=4401)
        return

    await ws_manager.connect(user_id, websocket)

    try:
        # просто держим соединение, ничего не ждём
        while True:
            # можно принимать "пинги" от клиента, чтобы соединение не засыпало
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(user_id, websocket)
    except Exception as e:
        print(f"[ws] unexpected error: {e}")
        await ws_manager.disconnect(user_id, websocket)