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
                temperature=1,
                top_p=0.95,
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

    def reply_stream(self, query, context: Context = None):
        """
        流式响应方法，返回一个生成器
        
        Args:
            query: 查询内容
            context: 上下文
            
        Yields:
            dict: 包含流式数据的字典
        """
        try:
            if context.type != ContextType.TEXT:
                logger.warn(f"[DynamicOpenAI] Unsupported message type for streaming, type={context.type}")
                return None
            
            logger.info(f"[DynamicOpenAI] Starting stream for query={query}")
            
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
            
            # 调用OpenAI API with stream=True
            chat_completion_res = client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=1,
                top_p=0.95,
                extra_body={},
                stream_options={"include_usage": True}
            )
            
            # 处理流式响应
            accumulated_text = ""
            estimated_prompt_tokens = len(str(messages)) // 4
            
            logger.info("[DynamicOpenAI] Starting to yield stream chunks...")
            
            for chunk in chat_completion_res:
                try:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        accumulated_text += content
                        
                        # 生成数据块
                        chunk_data = {
                            "content": content,
                            "accumulated_content": accumulated_text,
                            "finished": False,
                            # "token_usage": {
                            #     "prompt_tokens": estimated_prompt_tokens,
                            #     "completion_tokens": len(accumulated_text) // 4,
                            #     "total_tokens": estimated_prompt_tokens + len(accumulated_text) // 4
                            # }
                        }
                        
                        yield chunk_data
                        
                        # 控制台输出（可选）
                        print(content, end="", flush=True)
                
                except Exception as chunk_error:
                    logger.error(f"[DynamicOpenAI] Error processing chunk: {chunk_error}")
                    continue
            
            # 换行以保持日志清晰
            print()
            
            # 优化后的代码
            final_token_usage = {}
            if hasattr(chunk, 'usage') and chunk.usage:
                # 1. 安全地获取基础token数，如果不存在则默认为0
                prompt_tokens = getattr(chunk.usage, 'prompt_tokens', 0)
                completion_tokens = getattr(chunk.usage, 'completion_tokens', 0)

                # 2. 安全地处理非标准的 'reasoning_tokens'
                reasoning_tokens = 0
                if hasattr(chunk.usage, 'completion_tokens_details') and chunk.usage.completion_tokens_details:
                    reasoning_tokens = getattr(chunk.usage.completion_tokens_details, 'reasoning_tokens', 0)

                # 3. 计算最终的 completion_tokens
                final_completion_tokens = completion_tokens + reasoning_tokens
                
                # 4. 为保证一致性，重新计算 total_tokens
                final_total_tokens = prompt_tokens + final_completion_tokens

                final_token_usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": final_completion_tokens,
                    "total_tokens": final_total_tokens
                }
            
            logger.info(f"[DynamicOpenAI] Stream completed, total length: {len(accumulated_text)}")
            
            # 发送最终数据块（表示流结束）
            final_chunk = {
                "content": "",
                "accumulated_content": accumulated_text,
                "finished": True,
                "event": "end",
                "token_usage": final_token_usage
            }
            
            yield final_chunk
                
        except Exception as e:
            logger.error(f"[DynamicOpenAI] Error in stream processing: {str(e)}", exc_info=True)
            # 生成错误块
            error_chunk = {
                "error": f"Failed to invoke [DynamicOpenAI] streaming api: {str(e)}",
                "finished": True,
                "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            }
            yield error_chunk 