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
            "status": "Занята" if (len(r_data["players"]) >= 2 or r_data["mode"] == "pve") else "Очікування"
        })
    return JSONResponse(content=active_rooms_list)

games = {}

async def bot_play_turn(room_id, player_ws):
    bot = games[room_id]["bot"]
    player_board = games[room_id]["boards"][player_ws]
    while games[room_id].get("turn") == "bot":
        await asyncio.sleep(1.2)
        
        # ФІКС: Захист від того, щоб бот не завис, якщо випадково вистрілить туди, де вже стріляв
        while True:
            x, y = bot.get_next_shot()
            result, auto_misses = player_board.receive_shot(x, y)
            if result != "Вже було": 
                break
                
        # Передаємо боту авто-промахи
        bot.register_shot_result(x, y, result, auto_misses)
        
        await manager.send_personal_message({
            "type": "shoot_result", "x": x, "y": y, "status": result, 
            "is_mine": True, "auto_misses": auto_misses
        }, player_ws)
        
        if player_board.all_ships_sunk():
            await manager.send_personal_message({"type": "game_over", "message": "Бот переміг!"}, player_ws)
            await player_ws.close()
            return
            
        if result == "Мимо":
            games[room_id]["turn"] = player_ws
            await manager.send_personal_message({"type": "turn", "is_your_turn": True}, player_ws)
            
@app.websocket("/ws/game/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    # Извлекаем параметры вручную для надежности
    mode = websocket.query_params.get("mode", "pvp")
    nickname = websocket.query_params.get("nickname", "Анонім")
    
    if room_id in games and (games[room_id]["mode"] == "pve" or len(games[room_id]["players"]) >= 2):
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Кімната зайнята."})
        await websocket.close()
        return

    connected = await manager.connect(websocket, room_id)
    if not connected: return

    logging.info(f"Игрок '{nickname}' зашел в '{room_id}' (Мод: {mode})")

    if room_id not in games:
        games[room_id] = {
            "players": [], "boards": {}, "turn": None, "ready": {}, 
            "mode": mode, "bot": Bot(difficulty="medium") if mode == "pve" else None, 
            "started": False
        }
        if mode == "pve": 
            games[room_id]["bot"].auto_place_ships()
    
    games[room_id]["players"].append(websocket)
    games[room_id]["boards"][websocket] = Board()
    games[room_id]["ready"][websocket] = False

    # Небольшая пауза, чтобы клиент успел проинициализировать WebSocket.onmessage
    await asyncio.sleep(0.5)

    if mode == "pve" or len(games[room_id]["players"]) == 2:
        games[room_id]["turn"] = games[room_id]["players"][0]
        await manager.broadcast_to_room({
            "type": "game_phase", 
            "phase": "placement", 
            "message": "РОЗСТАВЛЯЙТЕ ФЛОТ!"
        }, room_id)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            # ... (остальная логика shoot и place_ships остается без изменений)
            if action == "place_ships" and not games[room_id]["started"]:
                board = games[room_id]["boards"][websocket]
                for s in data.get("ships", []): board.place_ship(s["x"], s["y"], s["length"], s["is_horizontal"])
                games[room_id]["ready"][websocket] = True
                if mode == "pve" or (len(games[room_id]["ready"]) == 2 and all(games[room_id]["ready"].values())):
                    games[room_id]["started"] = True
                    await manager.broadcast_to_room({"type": "game_phase", "phase": "playing", "message": "БІЙ ПОЧАВСЯ!"}, room_id)
                    for ws in games[room_id]["players"]: await manager.send_personal_message({"type": "turn", "is_your_turn": (ws == games[room_id]["turn"])}, ws)
            elif action == "shoot" and games[room_id]["turn"] == websocket:
                x, y = data.get("x"), data.get("y")
                is_pve = games[room_id]["mode"] == "pve"
                opp_board = games[room_id]["bot"].board if is_pve else games[room_id]["boards"][[ws for ws in games[room_id]["players"] if ws != websocket][0]]
                res, misses = opp_board.receive_shot(x, y)
                msg = {"type": "shoot_result", "x": x, "y": y, "status": res, "is_mine": False, "auto_misses": misses}
                await manager.send_personal_message(msg, websocket)
                if not is_pve:
                    opp_ws = [ws for ws in games[room_id]["players"] if ws != websocket][0]
                    msg["is_mine"] = True
                    await manager.send_personal_message(msg, opp_ws)
                if opp_board.all_ships_sunk():
                    await manager.broadcast_to_room({"type": "game_over", "message": "ПЕРЕМОГА!"}, room_id)
                    break
                if res == "Мимо":
                    if is_pve:
                        games[room_id]["turn"] = "bot"
                        await manager.send_personal_message({"type": "turn", "is_your_turn": False}, websocket)
                        asyncio.create_task(bot_play_turn(room_id, websocket))
                    else:
                        target_ws = [ws for ws in games[room_id]["players"] if ws != websocket][0]
                        games[room_id]["turn"] = target_ws
                        for ws in games[room_id]["players"]: await manager.send_personal_message({"type": "turn", "is_your_turn": (ws == games[room_id]["turn"])}, ws)
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        if room_id in games: del games[room_id]