# encoding:utf-8

"""
Dynamic OpenAI bot

@author: AI Assistant
@Date: 2025-01-21
"""

import openai
from bot.bot import Bot
from bridge.context import ContextType, Context
from bridge.reply import Reply, ReplyType
from common.log import logger


class DynamicOpenAIBot(Bot):
    def __init__(self, model_config):
        super().__init__()
        self.model_config = model_config
        self.model = model_config.get("model", "gpt-3.5-turbo")
        self.api_key = model_config.get("api_key")
        self.api_base = model_config.get("model_url")
        self.messages = model_config.get("messages", [])
        
        logger.info(f"[DynamicOpenAIBot] Initialized with model: {self.model}, base_url: {self.api_base}")

    def reply(self, query, context: Context = None) -> Reply:
        try:
            if context.type != ContextType.TEXT:
                logger.warn(f"[DynamicOpenAI] Unsupported message type, type={context.type}")
                return Reply(ReplyType.TEXT, None)
            
            logger.info(f"[DynamicOpenAI] query={query}")
            
            # 设置临时的API配置
            original_api_key = openai.api_key
            original_api_base = getattr(openai, 'api_base', None)
            
            openai.api_key = self.api_key
            if self.api_base:
                openai.api_base = self.api_base
            
            try:
                # 使用预处理后的完整messages
                messages = self.messages.copy()
                
                # 如果messages中没有当前query，说明是legacy格式，需要添加用户消息
                latest_user_msg = None
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        latest_user_msg = msg.get("content", "")
                        break
                
                if latest_user_msg != query:
                    logger.debug("[DynamicOpenAI] Adding current query as user message")
                    messages.append({"role": "user", "content": query})
                else:
                    logger.debug("[DynamicOpenAI] Using pre-processed messages")
                
                logger.debug(f"[DynamicOpenAI] Final messages count: {len(messages)}")
                
                # 调用OpenAI API
                response = openai.ChatCompletion.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.9,
                    # max_tokens=1200
                )
                
                reply_text = response.choices[0]["message"]["content"].strip()
                total_tokens = response["usage"]["total_tokens"]
                completion_tokens = response["usage"]["completion_tokens"]
                prompt_tokens = response["usage"]["prompt_tokens"]
                
                logger.info(f"[DynamicOpenAI] reply={reply_text}")
                
                # 构造token使用信息
                token_usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens
                }
                
                return Reply(ReplyType.TEXT, reply_text, token_usage)
                
            finally:
                # 恢复原始配置
                openai.api_key = original_api_key
                if original_api_base is not None:
                    openai.api_base = original_api_base
                
        except Exception as e:
            logger.error(f"[DynamicOpenAI] Error generating response: {str(e)}", exc_info=True)
            error_message = f"Failed to invoke [DynamicOpenAI] api: {str(e)}"
            return Reply(ReplyType.ERROR, error_message) 