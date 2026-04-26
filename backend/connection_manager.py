from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        # Зберігаємо кімнати. Ключ - ID кімнати, значення - список WebSocket з'єднань (гравців)
        self.active_rooms: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_rooms:
            self.active_rooms[room_id] = []
        
        if len(self.active_rooms[room_id]) < 2:
            self.active_rooms[room_id].append(websocket)
            return True
        else:
            # У кімнаті вже 2 людини, більше не можна
            await websocket.close(code=1000)
            return False

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_rooms:
            self.active_rooms[room_id].remove(websocket)
            if len(self.active_rooms[room_id]) == 0:
                del self.active_rooms[room_id]

    async def broadcast_to_room(self, message: dict, room_id: str):
        if room_id in self.active_rooms:
            for connection in self.active_rooms[room_id]:
                await connection.send_json(message)
                
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

manager = ConnectionManager()