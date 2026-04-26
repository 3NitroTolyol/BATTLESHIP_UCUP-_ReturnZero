from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from connection_manager import manager
from game_logic import Board

app = FastAPI()

# Роздаємо папку frontend. Шлях "../frontend" означає, що папка лежить на рівень вище за backend
app.mount("/static", StaticFiles(directory="../frontend"), name="static")

@app.get("/")
async def root():
    # Автоматично перекидаємо гравця на Головне Меню при заході на IP сервера
    return RedirectResponse(url="/static/index.html")

games = {}

@app.websocket("/ws/game/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    connected = await manager.connect(websocket, room_id)
    if not connected:
        return

    if room_id not in games:
        games[room_id] = {"players": [], "boards": {}, "turn": None, "ready": {}}
    
    games[room_id]["players"].append(websocket)
    games[room_id]["boards"][websocket] = Board()
    games[room_id]["ready"][websocket] = False

    players_count = len(games[room_id]["players"])
    await manager.broadcast_to_room({"type": "system", "message": f"Гравців у кімнаті: {players_count}/2"}, room_id)

    if players_count == 2:
        games[room_id]["turn"] = games[room_id]["players"][0] 
        await manager.broadcast_to_room({"type": "game_phase", "phase": "placement", "message": "Розставляйте кораблі!"}, room_id)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "place_ships":
                # ЗАХИСТ: Забороняємо надсилати розстановку двічі
                if games[room_id]["ready"].get(websocket):
                    continue 

                board = games[room_id]["boards"][websocket]
                ships_data = data.get("ships", [])
                
                for ship in ships_data:
                    board.place_ship(ship["x"], ship["y"], ship["length"], ship["is_horizontal"])
                
                games[room_id]["ready"][websocket] = True
                
                if len(games[room_id]["ready"]) == 2 and all(games[room_id]["ready"].values()):
                    await manager.broadcast_to_room({"type": "game_phase", "phase": "playing", "message": "Бій почався!"}, room_id)
                    for ws in games[room_id]["players"]:
                        await manager.send_personal_message({"type": "turn", "is_your_turn": (ws == games[room_id]["turn"])}, ws)

            elif action == "shoot":
                if games[room_id]["turn"] != websocket:
                    continue # ЗАХИСТ: Ігноруємо постріл, якщо не твоя черга
                
                x, y = data.get("x"), data.get("y")
                opponent_ws = [ws for ws in games[room_id]["players"] if ws != websocket][0]
                opponent_board = games[room_id]["boards"][opponent_ws]

                result = opponent_board.receive_shot(x, y)

                if result.startswith("Помилка"):
                    await manager.send_personal_message({"type": "error", "message": result}, websocket)
                    continue

                await manager.send_personal_message({"type": "shoot_result", "x": x, "y": y, "status": result, "is_mine": False}, websocket)
                await manager.send_personal_message({"type": "shoot_result", "x": x, "y": y, "status": result, "is_mine": True}, opponent_ws)

                if opponent_board.all_ships_sunk():
                    await manager.send_personal_message({"type": "game_over", "message": "Гра закінчена! Ти переміг!"}, websocket)
                    await manager.send_personal_message({"type": "game_over", "message": "Гра закінчена! Ти програв!"}, opponent_ws)
                    
                    # Принудительно закрываем вебсокеты обоих игроков
                    await websocket.close()
                    await opponent_ws.close()
                    # Это автоматически вызовет ошибку WebSocketDisconnect ниже по коду, 
                    # и сервер сам удалит комнату из словаря games!
                    continue

                if result == "Мимо":
                    games[room_id]["turn"] = opponent_ws
                
                for ws in games[room_id]["players"]:
                    await manager.send_personal_message({"type": "turn", "is_your_turn": (ws == games[room_id]["turn"])}, ws)

    except WebSocketDisconnect:
        # ФІКС БАГУ ОНОВЛЕННЯ: Повністю очищаємо стан кімнати
        manager.disconnect(websocket, room_id)
        if room_id in games:
            await manager.broadcast_to_room({"type": "game_over", "message": "Суперник вийшов. Гра закінчена."}, room_id)
            del games[room_id] # Видаляємо кімнату. Наступне підключення створить її з нуля.