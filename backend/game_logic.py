class Ship:
    def __init__(self, coordinates):
        # coordinates - це список кортежів (x, y), наприклад [(0,0), (0,1), (0,2)]
        self.coordinates = coordinates
        self.hits = set()

    def is_sunk(self):
        # Корабель потоплено, якщо кількість влучань дорівнює його довжині
        return len(self.hits) == len(self.coordinates)


class Board:
    def __init__(self):
        self.size = 10
        # Кодування клітинок: 0 - пусто, 1 - корабель, 2 - мимо, 3 - влучання
        self.grid = [[0 for _ in range(self.size)] for _ in range(self.size)]
        self.ships = []

    def is_valid_placement(self, x, y):
        """Перевіряє, чи можна поставити палубу в (x, y), щоб не було торкань."""
        # Перевірка виходу за межі поля
        if not (0 <= x < self.size and 0 <= y < self.size):
            return False
        
        # Перевірка сусідніх клітинок (включно з діагоналями)
        for i in range(-1, 2):
            for j in range(-1, 2):
                nx, ny = x + i, y + j
                if 0 <= nx < self.size and 0 <= ny < self.size:
                    if self.grid[nx][ny] == 1:
                        return False
        return True

    def place_ship(self, start_x, start_y, length, is_horizontal):
        """Намагається розмістити корабель. Повертає True, якщо успішно."""
        coords = []
        
        # Спочатку просто перевіряємо, чи поміститься весь корабель без порушень
        for i in range(length):
            x = start_x + (i if is_horizontal else 0)
            y = start_y + (0 if is_horizontal else i)
            
            if not self.is_valid_placement(x, y):
                return False
            coords.append((x, y))
        
        # Якщо все ок - ставимо корабель на дошку
        for x, y in coords:
            self.grid[x][y] = 1
        
        self.ships.append(Ship(coords))
        return True

    def receive_shot(self, x, y):
        """Обробка пострілу суперника. Повертає статус згідно з правилами."""
        if not (0 <= x < self.size and 0 <= y < self.size):
            return "Помилка: Поза межами поля"

        current_cell = self.grid[x][y]

        if current_cell == 0:
            self.grid[x][y] = 2  # Відмічаємо промах
            return "Мимо"
            
        elif current_cell == 1:
            self.grid[x][y] = 3  # Відмічаємо влучання
            
            # Шукаємо, в який саме корабель влучили
            for ship in self.ships:
                if (x, y) in ship.coordinates:
                    ship.hits.add((x, y))
                    if ship.is_sunk():
                        return "Потоплений"
                    return "Влучив"
                    
        elif current_cell in [2, 3]:
            return "Помилка: Вже стріляли сюди"

    def all_ships_sunk(self):
        """Перевірка завершення гри."""
        return all(ship.is_sunk() for ship in self.ships)