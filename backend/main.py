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

games = {}

async def bot_play_turn(room_id, player_ws):
    bot = games[room_id]["bot"]
    player_board = games[room_id]["boards"][player_ws]
    while games[room_id].get("turn") == "bot":
        await asyncio.sleep(1.2)
        while True:
            x, y = bot.get_next_shot()
            result, auto_misses = player_board.receive_shot(x, y)
            if result != "Вже було": break
                
        bot.register_shot_result(x, y, result, auto_misses)
        
        await manager.send_personal_message({
            "type": "shoot_result", "x": x, "y": y, "status": result, 
            "is_mine": True, "auto_misses": auto_misses
        }, player_ws)
        
        if player_board.all_ships_sunk():
            await manager.send_personal_message({"type": "game_over", "message": "ВОРОГ ПЕРЕМІГ! ФЛОТ ЗНИЩЕНО!"}, player_ws)
            await player_ws.close()
            return
            
        if result == "Мимо":
            games[room_id]["turn"] = player_ws
            await manager.send_personal_message({"type": "turn", "is_your_turn": True}, player_ws)

@app.websocket("/ws/game/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    mode = websocket.query_params.get("mode", "pvp")
    nickname = websocket.query_params.get("nickname", "Капітан")
    
    if room_id in games and (games[room_id]["mode"] == "pve" or len(games[room_id]["players"]) >= 2):
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
            "started": False, "superpower_used": {} # Додали словник для суперсили
        }
        if mode == "pve": games[room_id]["bot"].auto_place_ships()
    
    games[room_id]["players"].append(websocket)
    games[room_id]["boards"][websocket] = Board()
    games[room_id]["ready"][websocket] = False
    games[room_id]["superpower_used"][websocket] = False # Гровець ще не юзав суперсилу

    await asyncio.sleep(0.5)

    if mode == "pve" or len(games[room_id]["players"]) == 2:
        games[room_id]["turn"] = games[room_id]["players"][0]
        await manager.broadcast_to_room({"type": "game_phase", "phase": "placement", "message": "РОЗСТАВЛЯЙТЕ ФЛОТ!"}, room_id)

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            
            if action == "place_ships" and not games[room_id]["started"]:
                board = games[room_id]["boards"][websocket]
                for s in data.get("ships", []): board.place_ship(s["x"], s["y"], s["length"], s["is_horizontal"])
                games[room_id]["ready"][websocket] = True
                if mode == "pve" or (len(games[room_id]["ready"]) == 2 and all(games[room_id]["ready"].values())):
                    games[room_id]["started"] = True
                    await manager.broadcast_to_room({"type": "game_phase", "phase": "playing", "message": "БІЙ ПОЧАВСЯ!"}, room_id)
                    for ws in games[room_id]["players"]: await manager.send_personal_message({"type": "turn", "is_your_turn": (ws == games[room_id]["turn"])}, ws)
            
            elif action in ["shoot", "super_shoot"] and games[room_id]["turn"] == websocket:
                x, y = data.get("x"), data.get("y")
                is_pve = games[room_id]["mode"] == "pve"
                opp_board = games[room_id]["bot"].board if is_pve else games[room_id]["boards"][[ws for ws in games[room_id]["players"] if ws != websocket][0]]
                
                shots_to_process = []
                if action == "super_shoot":
                    if games[room_id]["superpower_used"].get(websocket, False): continue
                    games[room_id]["superpower_used"][websocket] = True
                    # Генеруємо 9 пострілів (3х3)
                    for dx in [-1, 0, 1]:
                        for dy in [-1, 0, 1]:
                            if 0 <= x+dx < 10 and 0 <= y+dy < 10: shots_to_process.append((x+dx, y+dy))
                else:
                    shots_to_process.append((x, y))

                hit_occurred = False
                for sx, sy in shots_to_process:
                    res, misses = opp_board.receive_shot(sx, sy)
                    if res != "Вже було":
                        if res in ["Влучив", "Потоплений"]: hit_occurred = True
                        msg = {"type": "shoot_result", "x": sx, "y": sy, "status": res, "is_mine": False, "auto_misses": misses}
                        await manager.send_personal_message(msg, websocket)
                        if not is_pve:
                            opp_ws = [ws for ws in games[room_id]["players"] if ws != websocket][0]
                            msg_opp = msg.copy()
                            msg_opp["is_mine"] = True
                            await manager.send_personal_message(msg_opp, opp_ws)

                if opp_board.all_ships_sunk():
                    await manager.broadcast_to_room({"type": "game_over", "message": "ПЕРЕМОГА! ФЛОТ ВОРОГА ЗНИЩЕНО!"}, room_id)
                    break
                
                # Якщо хоча б одне влучання з 3х3 було - хід залишається
                if not hit_occurred:
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