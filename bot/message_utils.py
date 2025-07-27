import json
import os
from typing import Dict, Any

class MessageManager:
    def __init__(self, messages_file: str = "bot/messages.json"):
        self.messages_file = messages_file
        self.messages = self._load_messages()
    
    def _load_messages(self) -> Dict[str, Any]:
        """Загружает сообщения из JSON файла"""
        try:
            with open(self.messages_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Файл сообщений не найден: {self.messages_file}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Ошибка парсинга JSON файла: {e}")
    
    def get_message(self, *keys: str, **kwargs) -> str:
        """
        Получает сообщение по ключам и форматирует его с переданными параметрами
        
        Args:
            *keys: Ключи для поиска сообщения (например: 'giveaway', 'create', 'success')
            **kwargs: Параметры для форматирования строки
        
        Returns:
            str: Сообщение или пустая строка, если не найдено
        """
        try:
            message = self.messages
            for key in keys:
                message = message[key]
            
            if isinstance(message, str):
                return message.format(**kwargs) if kwargs else message
            else:
                return ""
        except (KeyError, TypeError):
            return ""
    
    def reload_messages(self):
        """Перезагружает сообщения из файла"""
        self.messages = self._load_messages()

# Глобальный экземпляр менеджера сообщений
message_manager = MessageManager() 