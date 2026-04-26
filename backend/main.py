import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from connection_manager import manager
from game_logic import Board, Bot 

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()
app.mount("/static", StaticFiles(directory="../frontend"), name="static")
# У main.py додаємо цей рядок:
app.mount("/assets", StaticFiles(directory="../assets"), name="assets")

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")

@app.get("/rooms")
async def get_active_rooms():
    active_rooms_list = []
    for r_id, r_data in games.items():
        active_rooms_list.append({
            "id": r_id,
            "players": len(r_data["players"]),
            "mode": r_data["mode"],
            "status": "Зайнята" if (len(r_data["players"]) >= 2 or r_data["mode"] == "pve") else "Очікування"
        })
    return JSONResponse(content=active_rooms_list)

games = {}

async def bot_play_turn(room_id, player_ws):
    bot = games[room_id]["bot"]
    player_board = games[room_id]["boards"][player_ws]
    
    while games[room_id].get("turn") == "bot":
        await asyncio.sleep(1.2)
        x, y = bot.get_next_shot()
        result, auto_misses = player_board.receive_shot(x, y)
        bot.register_shot_result(x, y, result)
        
        await manager.send_personal_message({
            "type": "shoot_result", "x": x, "y": y, "status": result, 
            "is_mine": True, "auto_misses": auto_misses
        }, player_ws)

        if player_board.all_ships_sunk():
            await manager.send_personal_message({"type": "game_over", "message": "Бот переміг! Не здавайтеся, капітане!"}, player_ws)
            await player_ws.close()
            return

        if result == "Мимо":
            games[room_id]["turn"] = player_ws
            await manager.send_personal_message({"type": "turn", "is_your_turn": True}, player_ws)

@app.websocket("/ws/game/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, mode: str = "pvp", nickname: str = "Анонім"):
    if room_id in games:
        if games[room_id]["mode"] == "pve" or len(games[room_id]["players"]) >= 2:
            await websocket.accept()
            await websocket.send_json({"type": "error", "message": "Кімната зайнята."})
            await websocket.close()
            return

    connected = await manager.connect(websocket, room_id)
    if not connected: return

    if room_id not in games:
        games[room_id] = {
            "players": [], "boards": {}, "turn": None, "ready": {}, 
            "mode": mode, "bot": Bot(difficulty="medium") if mode == "pve" else None,
            "started": False # Додаємо прапорець, що гра почалася
        }
        if mode == "pve": games[room_id]["bot"].auto_place_ships()
    
    games[room_id]["players"].append(websocket)
    games[room_id]["boards"][websocket] = Board()
    games[room_id]["ready"][websocket] = False

    if mode == "pve" or len(games[room_id]["players"]) == 2:
        games[room_id]["turn"] = games[room_id]["players"][0]
        await manager.broadcast_to_room({"type": "game_phase", "phase": "placement", "message": "Розставляйте флот!"}, room_id)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "place_ships":
                # ЗАХИСТ: якщо гра вже йде, ігноруємо розстановку
                if games[room_id]["started"]: continue
                
                board = games[room_id]["boards"][websocket]
                for s in data.get("ships", []):
                    board.place_ship(s["x"], s["y"], s["length"], s["is_horizontal"])
                
                games[room_id]["ready"][websocket] = True
                
                if mode == "pve" or (len(games[room_id]["ready"]) == 2 and all(games[room_id]["ready"].values())):
                    games[room_id]["started"] = True # ГРА ПОЧАЛАСЯ
                    await manager.broadcast_to_room({"type": "game_phase", "phase": "playing", "message": "Бій почався! Вогонь!"}, room_id)
                    for ws in games[room_id]["players"]:
                        await manager.send_personal_message({"type": "turn", "is_your_turn": (ws == games[room_id]["turn"])}, ws)

            elif action == "shoot":
                if games[room_id]["turn"] != websocket: continue
                x, y = data.get("x"), data.get("y")
                is_pve = games[room_id]["mode"] == "pve"
                opponent_board = games[room_id]["bot"].board if is_pve else \
                                 games[room_id]["boards"][[ws for ws in games[room_id]["players"] if ws != websocket][0]]
                
                result, auto_misses = opponent_board.receive_shot(x, y)
                if result == "Вже було": continue

                msg = {"type": "shoot_result", "x": x, "y": y, "status": result, "is_mine": False, "auto_misses": auto_misses}
                await manager.send_personal_message(msg, websocket)
                
                if not is_pve:
                    opponent_ws = [ws for ws in games[room_id]["players"] if ws != websocket][0]
                    msg["is_mine"] = True
                    await manager.send_personal_message(msg, opponent_ws)

                if opponent_board.all_ships_sunk():
                    await manager.broadcast_to_room({"type": "game_over", "message": "Перемога! Весь ворожий флот на дні!"}, room_id)
                    await asyncio.sleep(1)
                    await websocket.close()
                    break

                if result == "Мимо":
                    if is_pve:
                        games[room_id]["turn"] = "bot"
                        await manager.send_personal_message({"type": "turn", "is_your_turn": False}, websocket)
                        asyncio.create_task(bot_play_turn(room_id, websocket))
                    else:
                        opponent_ws = [ws for ws in games[room_id]["players"] if ws != websocket][0]
                        games[room_id]["turn"] = opponent_ws
                        for ws in games[room_id]["players"]:
                            await manager.send_personal_message({"type": "turn", "is_your_turn": (ws == games[room_id]["turn"])}, ws)

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        if room_id in games: del games[room_id]