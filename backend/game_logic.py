import random

class Ship:
    def __init__(self, coordinates):
        self.coordinates = coordinates
        self.hits = set()
    def is_sunk(self): return len(self.hits) == len(self.coordinates)

class Board:
    def __init__(self):
        self.grid = [[0 for _ in range(10)] for _ in range(10)]
        self.ships = []
    def place_ship(self, sx, sy, length, is_hor):
        coords = []
        for i in range(length):
            x, y = (sx + i, sy) if is_hor else (sx, sy + i)
            if not (0 <= x < 10 and 0 <= y < 10) or any(self.grid[nx][ny] == 1 for nx in range(max(0, x-1), min(10, x+2)) for ny in range(max(0, y-1), min(10, y+2))): return False
            coords.append((x, y))
        for x, y in coords: self.grid[x][y] = 1
        self.ships.append(Ship(coords)); return True
    def receive_shot(self, x, y):
        if self.grid[x][y] == 0: self.grid[x][y] = 2; return "Мимо", []
        if self.grid[x][y] == 1:
            self.grid[x][y] = 3
            for s in self.ships:
                if (x, y) in s.coordinates:
                    s.hits.add((x, y))
                    if s.is_sunk():
                        misses = [(nx, ny) for cx, cy in s.coordinates for nx in range(cx-1, cx+2) for ny in range(cy-1, cy+2) if 0 <= nx < 10 and 0 <= ny < 10 and self.grid[nx][ny] == 0]
                        for mx, my in misses: self.grid[mx][my] = 2
                        return "Потоплений", misses
                    return "Влучив", []
        return "Вже було", []
    def all_ships_sunk(self): return not any(1 in row for row in self.grid)

class Bot:
    def __init__(self, difficulty="medium"):
        self.difficulty, self.board, self.shots, self.hunt = difficulty, Board(), set(), []
        
    def auto_place_ships(self):
        for length in [4, 3, 3, 2, 2, 2, 1, 1, 1, 1]:
            while not self.board.place_ship(random.randint(0, 9), random.randint(0, 9), length, random.choice([True, False])): pass
            
    def get_next_shot(self):
        while self.hunt:
            shot = self.hunt.pop(0)
            if shot not in self.shots: self.shots.add(shot); return shot
        while True:
            shot = (random.randint(0, 9), random.randint(0, 9))
            if shot not in self.shots: self.shots.add(shot); return shot
            
    # ФІКС: Бот тепер приймає auto_misses і очищає чергу при потопленні
    def register_shot_result(self, x, y, res, auto_misses=None):
        if self.difficulty == "medium" and res == "Влучив":
            for nx, ny in [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]:
                if 0 <= nx < 10 and 0 <= ny < 10 and (nx, ny) not in self.shots: self.hunt.append((nx, ny))
        elif res == "Потоплений":
            self.hunt = [] # Очищаємо пам'ять добивання!
            if auto_misses:
                for mx, my in auto_misses: self.shots.add((mx, my)) # Бот запам'ятовує крапки