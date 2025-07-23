# encoding:utf-8

"""
Dynamic Google Gemini bot

@author: AI Assistant
@Date: 2025-01-21
"""

from bot.bot import Bot
from google import genai
from bridge.context import ContextType, Context
from bridge.reply import Reply, ReplyType
from common.log import logger
from bot.gemini.dynamic_gemini_session import DynamicGeminiSession


class DynamicGeminiBot(Bot):
    def __init__(self, model_config):
        super().__init__()
        self.model_config = model_config
        self.model = model_config.get("model", "gemini-pro")
        self.api_key = model_config.get("api_key")
        self.api_base = model_config.get("model_url")
        
        # 创建动态session管理器
        self.session = DynamicGeminiSession(model_config)
        
        logger.info(f"[DynamicGeminiBot] Initialized with model: {self.model}, base_url: {self.api_base}")

    def reply(self, query, context: Context = None) -> Reply:
        try:
            if context.type != ContextType.TEXT:
                logger.warn(f"[DynamicGemini] Unsupported message type, type={context.type}")
                return Reply(ReplyType.TEXT, None)
            
            logger.info(f"[DynamicGemini] query={query}")
            
            # 使用动态session处理消息
            gemini_messages = self.session.get_messages_for_api()
            logger.debug(f"[DynamicGemini] messages={gemini_messages}")
            
            # 创建客户端
            client = genai.Client(
                http_options={"base_url": self.api_base},
                api_key=self.api_key,
            )
            
            # 生成回复
            response = client.models.generate_content(
                model=self.model,
                contents=gemini_messages
            )
            
            if response.candidates and response.candidates[0].content:
                reply_text = response.candidates[0].content.parts[0].text
                logger.info(f"[DynamicGemini] reply={reply_text}")
                
                # 更新session
                self.session.add_assistant_message(reply_text)
                
                # 构造token使用信息（Gemini API可能不返回详细token信息，这里模拟）
                token_usage = {
                    "prompt_tokens": len(str(gemini_messages)) // 4,  # 粗略估算
                    "completion_tokens": len(reply_text) // 4,  # 粗略估算
                    "total_tokens": (len(str(gemini_messages)) + len(reply_text)) // 4
                }
                
                return Reply(ReplyType.TEXT, reply_text, token_usage)
            else:
                logger.warning("[DynamicGemini] No valid response generated")
                error_message = "No valid response generated"
                return Reply(ReplyType.ERROR, error_message)
                    
        except Exception as e:
            logger.error(f"[DynamicGemini] Error generating response: {str(e)}", exc_info=True)
            error_message = f"Failed to invoke [DynamicGemini] api: {str(e)}"
            return Reply(ReplyType.ERROR, error_message) 