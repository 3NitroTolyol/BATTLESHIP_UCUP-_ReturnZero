import random

class Ship:
    def __init__(self, coordinates):
        self.coordinates = coordinates
        self.hits = set()

    def is_sunk(self):
        return len(self.hits) == len(self.coordinates)

class Board:
    def __init__(self):
        self.size = 10
        self.grid = [[0 for _ in range(self.size)] for _ in range(self.size)]
        self.ships = []

    def is_valid_placement(self, x, y):
        if not (0 <= x < self.size and 0 <= y < self.size):
            return False
        for i in range(-1, 2):
            for j in range(-1, 2):
                nx, ny = x + i, y + j
                if 0 <= nx < self.size and 0 <= ny < self.size:
                    if self.grid[nx][ny] == 1:
                        return False
        return True

    def place_ship(self, start_x, start_y, length, is_horizontal):
        coords = []
        for i in range(length):
            x = start_x + (i if is_horizontal else 0)
            y = start_y + (0 if is_horizontal else i)
            if not self.is_valid_placement(x, y):
                return False
            coords.append((x, y))
        
        for x, y in coords:
            self.grid[x][y] = 1
        
        self.ships.append(Ship(coords))
        return True

    def get_surrounding_cells(self, ship):
        """Повертає список координат навколо корабля для авто-промахів"""
        surrounding = set()
        for x, y in ship.coordinates:
            for i in range(-1, 2):
                for j in range(-1, 2):
                    nx, ny = x + i, y + j
                    if 0 <= nx < 10 and 0 <= ny < 10:
                        if (nx, ny) not in ship.coordinates:
                            surrounding.add((nx, ny))
        return list(surrounding)

    def receive_shot(self, x, y):
        current_cell = self.grid[x][y]
        if current_cell == 0:
            self.grid[x][y] = 2
            return "Мимо", []
            
        elif current_cell == 1:
            self.grid[x][y] = 3
            for ship in self.ships:
                if (x, y) in ship.coordinates:
                    ship.hits.add((x, y))
                    if ship.is_sunk():
                        # Якщо потоплений, повертаємо координати навколо нього
                        auto_misses = self.get_surrounding_cells(ship)
                        for mx, my in auto_misses:
                            if self.grid[mx][my] == 0: # Тільки якщо там було пусто
                                self.grid[mx][my] = 2
                        return "Потоплений", auto_misses
                    return "Влучив", []
        return "Вже було", []

    def all_ships_sunk(self):
        # Перевірка: чи є хоча б одна клітинка з '1' (корабель) на полі
        for row in self.grid:
            if 1 in row:
                return False
        return True
    




class Bot:
    def __init__(self, difficulty="easy"):
        self.difficulty = difficulty
        self.board = Board()
        self.shots_fired = set()  # Клітинки, куди бот вже стріляв
        
        # Для середнього рівня складності (Hunt & Target)
        self.last_hit = None      # Координати останнього влучання
        self.hunt_queue = []      # Черга клітинок для "добивання"

    def auto_place_ships(self):
        """Автоматична випадкова розстановка флоту для бота"""
        fleet = [4, 3, 3, 2, 2, 2, 1, 1, 1, 1]
        for length in fleet:
            placed = False
            while not placed:
                x = random.randint(0, 9)
                y = random.randint(0, 9)
                is_horizontal = random.choice([True, False])
                placed = self.board.place_ship(x, y, length, is_horizontal)

    def get_next_shot(self):
        """Повертає координати (x, y) для наступного пострілу бота"""
        if self.difficulty == "medium" and self.hunt_queue:
            # Добиваємо поранений корабель
            shot = self.hunt_queue.pop(0)
            # Перевіряємо, чи ми сюди вже не стріляли
            while shot in self.shots_fired and self.hunt_queue:
                shot = self.hunt_queue.pop(0)
            if shot not in self.shots_fired:
                self.shots_fired.add(shot)
                return shot

        # Легкий рівень або звичайний пошук (випадковий постріл)
        while True:
            x = random.randint(0, 9)
            y = random.randint(0, 9)
            if (x, y) not in self.shots_fired:
                self.shots_fired.add((x, y))
                return x, y

    def register_shot_result(self, x, y, result):
        """Бот аналізує результат свого пострілу"""
        if self.difficulty == "medium":
            if result == "Влучив":
                self.last_hit = (x, y)
                # Додаємо сусідні клітинки в чергу на добивання (хрестиком)
                neighbors = [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]
                for nx, ny in neighbors:
                    if 0 <= nx < 10 and 0 <= ny < 10 and (nx, ny) not in self.shots_fired:
                        self.hunt_queue.append((nx, ny))
            elif result == "Потоплений":
                self.last_hit = None
                self.hunt_queue = [] # Корабель знищено, повертаємось до пошуку   