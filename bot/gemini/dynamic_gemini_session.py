# encoding:utf-8

"""
Dynamic Gemini Session

@author: AI Assistant
@Date: 2025-01-21
"""

from common.log import logger


class DynamicGeminiSession:
    def __init__(self, model_config):
        self.model_config = model_config
        self.messages = []
        
        # 从前端传入的messages初始化会话
        input_messages = model_config.get("messages", [])
        if input_messages:
            self.messages = input_messages.copy()
            logger.info(f"[DynamicGeminiSession] Initialized with {len(input_messages)} messages")
        else:
            logger.info("[DynamicGeminiSession] Initialized with empty session")

    def add_user_message(self, content):
        """添加用户消息"""
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content):
        """添加助手消息"""
        self.messages.append({"role": "assistant", "content": content})

    def get_messages_for_api(self):
        """转换消息格式为Gemini API所需的格式"""
        gemini_messages = []
        
        for msg in self.messages:
            role = msg.get("role")
            content = msg.get("content", "")
            
            if role == "system":
                # Gemini中system消息转换为user消息
                gemini_role = "user"
            elif role == "user":
                gemini_role = "user"
            elif role == "assistant":
                gemini_role = "model"
            else:
                continue
            
            gemini_messages.append({
                "role": gemini_role,
                "parts": [{"text": content}]
            })
        
        return gemini_messages

    def clear(self):
        """清空会话"""
        self.messages = []

    def get_message_count(self):
        """获取消息数量"""
        return len(self.messages) 