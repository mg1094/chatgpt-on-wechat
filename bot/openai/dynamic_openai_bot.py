# encoding:utf-8

"""
Dynamic OpenAI bot

@author: AI Assistant
@Date: 2025-01-21
"""

from openai import OpenAI
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
        
        # 流式输出配置（默认启用）
        self.enable_stream = model_config.get("stream", False)
        
        logger.info(f"[DynamicOpenAIBot] Initialized with model: {self.model}, base_url: {self.api_base}, stream: {self.enable_stream}")

    def reply(self, query, context: Context = None) -> Reply:
        try:
            if context.type != ContextType.TEXT:
                logger.warn(f"[DynamicOpenAI] Unsupported message type, type={context.type}")
                return Reply(ReplyType.TEXT, None)
            
            logger.info(f"[DynamicOpenAI] query={query}")
            
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
            
            # 创建 OpenAI 客户端
            client = OpenAI(
                base_url=self.api_base,
                api_key=self.api_key,
            )
            
            # 根据配置决定是否启用流式输出
            stream = self.enable_stream
            max_tokens = 1000
            response_format = {"type": "text"}
            
            # 调用OpenAI API
            chat_completion_res = client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=stream,
                temperature=0.9,                            
                extra_body={}
            )

            if stream:
                # 流式处理响应
                reply_text = ""
                logger.info("[DynamicOpenAI] Starting stream response...")
                
                for chunk in chat_completion_res:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        reply_text += content
                        # 实时输出到控制台（可选）
                        print(content, end="", flush=True)
                
                # 换行以保持日志清晰
                print()
                
                # 流式模式下无法获取准确的token使用情况，使用估算
                estimated_prompt_tokens = len(str(messages)) // 4
                estimated_completion_tokens = len(reply_text) // 4
                estimated_total_tokens = estimated_prompt_tokens + estimated_completion_tokens
                
                logger.info(f"[DynamicOpenAI] Stream completed, reply length: {len(reply_text)}")
                
                token_usage = {
                    "prompt_tokens": estimated_prompt_tokens,
                    "completion_tokens": estimated_completion_tokens,
                    "total_tokens": estimated_total_tokens
                }
                
            else:
                # 非流式模式
                reply_text = chat_completion_res.choices[0].message.content.strip()
                
                # 从响应中获取准确的token使用信息
                if hasattr(chat_completion_res, 'usage') and chat_completion_res.usage:
                    total_tokens = chat_completion_res.usage.total_tokens
                    completion_tokens = chat_completion_res.usage.completion_tokens
                    prompt_tokens = chat_completion_res.usage.prompt_tokens
                else:
                    # 如果没有usage信息，使用估算
                    prompt_tokens = len(str(messages)) // 4
                    completion_tokens = len(reply_text) // 4
                    total_tokens = prompt_tokens + completion_tokens
                
                logger.info(f"[DynamicOpenAI] Non-stream reply={reply_text}")
                
                token_usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens
                }
            
            logger.info(f"[DynamicOpenAI] Final reply length: {len(reply_text)}")
            return Reply(ReplyType.TEXT, reply_text.strip(), token_usage)
                
        except Exception as e:
            logger.error(f"[DynamicOpenAI] Error generating response: {str(e)}", exc_info=True)
            error_message = f"Failed to invoke [DynamicOpenAI] api: {str(e)}"
            return Reply(ReplyType.ERROR, error_message) 