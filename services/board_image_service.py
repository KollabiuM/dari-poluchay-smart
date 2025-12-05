"""
Сервис генерации изображений досок.
Создаёт картинку с логинами участников на их позициях.
"""
import os
from io import BytesIO
from typing import Optional, Dict

from PIL import Image, ImageDraw, ImageFont

from models.table import Table, LEVELS


# Путь к шаблону доски
TEMPLATE_PATH = "assets/board_template.png"
# Путь к шрифту (можно использовать системный)
FONT_PATH = "assets/fonts/arial.ttf"


# Координаты позиций на изображении (x, y)
# Настрой под свой шаблон!
POSITIONS = {
    # Получатель (центр сверху)
    'rec': (400, 180),
    
    # Создатели
    'crl': (250, 280),
    'crr': (550, 280),
    
    # Строители
    'stl1': (150, 380),
    'stl2': (300, 380),
    'str3': (500, 380),
    'str4': (650, 380),
    
    # Дарители (левая сторона)
    'dl1': (80, 500),
    'dl2': (180, 500),
    'dl3': (280, 500),
    'dl4': (380, 500),
    
    # Дарители (правая сторона)
    'dr5': (420, 500),
    'dr6': (520, 500),
    'dr7': (620, 500),
    'dr8': (720, 500),
}

# Цвета
COLORS = {
    'rec': (255, 215, 0),      # Золотой - получатель
    'creator': (0, 191, 255),   # Голубой - создатели
    'builder': (50, 205, 50),   # Зелёный - строители
    'donor_paid': (0, 255, 0),  # Ярко-зелёный - оплатил
    'donor_wait': (255, 165, 0), # Оранжевый - ждёт оплаты
    'empty': (128, 128, 128),   # Серый - пусто
    'highlight': (255, 0, 0),   # Красный - текущий пользователь
    'referral': (0, 100, 255),  # Синий - реферал 1-й линии
}


class BoardImageService:
    """Сервис генерации изображений досок."""
    
    def __init__(self):
        self.template_path = TEMPLATE_PATH
        self.font_path = FONT_PATH
        self.positions = POSITIONS
    
    async def generate_board_image(
        self,
        table: Table,
        user_map: Dict[int, str],
        current_user_tid: Optional[int] = None,
        referral_tids: Optional[list] = None,
    ) -> BytesIO:
        """
        Генерирует изображение доски с логинами.
        
        Args:
            table: Объект доски
            user_map: Словарь {tid: display_name}
            current_user_tid: tid текущего пользователя (подсветка красным)
            referral_tids: Список tid рефералов 1-й линии (подсветка синим)
            
        Returns:
            BytesIO с изображением PNG
        """
        referral_tids = referral_tids or []
        
        # Загружаем шаблон или создаём пустой
        if os.path.exists(self.template_path):
            img = Image.open(self.template_path).convert('RGBA')
        else:
            # Создаём простой шаблон если файла нет
            img = self._create_default_template(table)
        
        draw = ImageDraw.Draw(img)
        
        # Загружаем шрифт
        try:
            font = ImageFont.truetype(self.font_path, 20)
            font_small = ImageFont.truetype(self.font_path, 16)
            font_title = ImageFont.truetype(self.font_path, 28)
        except:
            # Используем встроенный шрифт
            font = ImageFont.load_default()
            font_small = font
            font_title = font
        
        # Рисуем заголовок
        level_info = LEVELS.get(table.level, {})
        title = f"{level_info.get('name', 'Доска')} (#{table.id})"
        self._draw_centered_text(draw, title, (img.width // 2, 50), font_title, (255, 255, 255))
        
        # Рисуем участников
        slots = {
            'rec': (table.rec, None),
            'crl': (table.crl, None),
            'crr': (table.crr, None),
            'stl1': (table.stl1, None),
            'stl2': (table.stl2, None),
            'str3': (table.str3, None),
            'str4': (table.str4, None),
            'dl1': (table.dl1, table.dl1_pay),
            'dl2': (table.dl2, table.dl2_pay),
            'dl3': (table.dl3, table.dl3_pay),
            'dl4': (table.dl4, table.dl4_pay),
            'dr5': (table.dr5, table.dr5_pay),
            'dr6': (table.dr6, table.dr6_pay),
            'dr7': (table.dr7, table.dr7_pay),
            'dr8': (table.dr8, table.dr8_pay),
        }
        
        for slot_name, (tid, is_paid) in slots.items():
            pos = self.positions.get(slot_name)
            if not pos:
                continue
            
            # Определяем текст и цвет
            if tid:
                name = user_map.get(tid, f"ID:{tid}")
                # Укорачиваем длинные имена
                if len(name) > 12:
                    name = name[:10] + ".."
                
                # Определяем цвет
                if tid == current_user_tid:
                    color = COLORS['highlight']  # Красный - это вы
                elif tid in referral_tids:
                    color = COLORS['referral']   # Синий - ваш реферал
                elif slot_name == 'rec':
                    color = COLORS['rec']
                elif slot_name.startswith('cr'):
                    color = COLORS['creator']
                elif slot_name.startswith('st'):
                    color = COLORS['builder']
                elif is_paid:
                    color = COLORS['donor_paid']
                else:
                    color = COLORS['donor_wait']
            else:
                name = "Свободно"
                color = COLORS['empty']
            
            # Рисуем подложку
            self._draw_slot_background(draw, pos, color)
            
            # Рисуем текст
            self._draw_centered_text(draw, name, pos, font_small, (255, 255, 255))
        
        # Рисуем легенду
        self._draw_legend(draw, img, font_small)
        
        # Сохраняем в BytesIO
        output = BytesIO()
        img.save(output, format='PNG')
        output.seek(0)
        
        return output
    
    def _create_default_template(self, table: Table) -> Image.Image:
        """Создаёт простой шаблон доски."""
        width, height = 800, 650
        img = Image.new('RGBA', (width, height), (30, 40, 50, 255))
        
        draw = ImageDraw.Draw(img)
        
        # Рисуем "доску" (фон)
        draw.rounded_rectangle(
            [(50, 100), (750, 580)],
            radius=20,
            fill=(60, 70, 60),
            outline=(100, 120, 100),
            width=3
        )
        
        # Линии связей (упрощённые)
        # REC -> Creators
        draw.line([self.positions['rec'], self.positions['crl']], fill=(150, 150, 150), width=2)
        draw.line([self.positions['rec'], self.positions['crr']], fill=(150, 150, 150), width=2)
        
        # Creators -> Builders
        draw.line([self.positions['crl'], self.positions['stl1']], fill=(150, 150, 150), width=2)
        draw.line([self.positions['crl'], self.positions['stl2']], fill=(150, 150, 150), width=2)
        draw.line([self.positions['crr'], self.positions['str3']], fill=(150, 150, 150), width=2)
        draw.line([self.positions['crr'], self.positions['str4']], fill=(150, 150, 150), width=2)
        
        return img
    
    def _draw_slot_background(self, draw: ImageDraw, pos: tuple, color: tuple):
        """Рисует фон для слота."""
        x, y = pos
        padding = 45
        draw.rounded_rectangle(
            [(x - padding, y - 15), (x + padding, y + 15)],
            radius=8,
            fill=(*color, 200),
            outline=(255, 255, 255, 100),
            width=1
        )
    
    def _draw_centered_text(
        self,
        draw: ImageDraw,
        text: str,
        pos: tuple,
        font: ImageFont,
        color: tuple
    ):
        """Рисует текст по центру позиции."""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = pos[0] - text_width // 2
        y = pos[1] - text_height // 2
        
        # Тень
        draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 128))
        # Основной текст
        draw.text((x, y), text, font=font, fill=color)
    
    def _draw_legend(self, draw: ImageDraw, img: Image.Image, font: ImageFont):
        """Рисует легенду."""
        legend_y = img.height - 40
        legend_items = [
            ("🔴 Вы", COLORS['highlight']),
            ("🔵 Реферал", COLORS['referral']),
            ("✅ Оплачено", COLORS['donor_paid']),
            ("⏳ Ждёт", COLORS['donor_wait']),
        ]
        
        x_offset = 100
        for text, color in legend_items:
            draw.rounded_rectangle(
                [(x_offset - 5, legend_y - 8), (x_offset + 5, legend_y + 8)],
                radius=3,
                fill=color
            )
            draw.text((x_offset + 15, legend_y - 8), text, font=font, fill=(200, 200, 200))
            x_offset += 150


# Singleton
_board_image_service = None

def get_board_image_service() -> BoardImageService:
    """Получить сервис генерации изображений."""
    global _board_image_service
    if _board_image_service is None:
        _board_image_service = BoardImageService()
    return _board_image_service
