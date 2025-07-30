from bot.bot_factory import create_bot
from bridge.context import Context
from bridge.reply import Reply
from common import const
from common.log import logger
from common.singleton import singleton
from config import conf
from translate.factory import create_translator
from voice.factory import create_voice


@singleton
class Bridge(object):
    def __init__(self):
        self.btype = {
            "chat": const.CHATGPT,
            "voice_to_text": conf().get("voice_to_text", "openai"),
            "text_to_voice": conf().get("text_to_voice", "google"),
            "translate": conf().get("translate", "baidu"),
        }
        # 这边取配置的模型
        bot_type = conf().get("bot_type")
        if bot_type:
            self.btype["chat"] = bot_type
        else:
            model_type = conf().get("model") or const.GPT35
            if model_type in ["text-davinci-003"]:
                self.btype["chat"] = const.OPEN_AI
            if conf().get("use_azure_chatgpt", False):
                self.btype["chat"] = const.CHATGPTONAZURE
            if model_type in ["wenxin", "wenxin-4"]:
                self.btype["chat"] = const.BAIDU
            if model_type in ["xunfei"]:
                self.btype["chat"] = const.XUNFEI
            if model_type in [const.QWEN]:
                self.btype["chat"] = const.QWEN
            if model_type in [const.QWEN_TURBO, const.QWEN_PLUS, const.QWEN_MAX]:
                self.btype["chat"] = const.QWEN_DASHSCOPE
            if model_type and model_type.startswith("gemini"):
                self.btype["chat"] = const.GEMINI
            if model_type and model_type.startswith("glm"):
                self.btype["chat"] = const.ZHIPU_AI
            if model_type and model_type.startswith("claude"):
                self.btype["chat"] = const.CLAUDEAPI

            if model_type in ["claude"]:
                self.btype["chat"] = const.CLAUDEAI

            if model_type in [const.MOONSHOT, "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]:
                self.btype["chat"] = const.MOONSHOT

            if model_type in [const.MODELSCOPE]:
                self.btype["chat"] = const.MODELSCOPE
            
            if model_type in ["abab6.5-chat"]:
                self.btype["chat"] = const.MiniMax

            if conf().get("use_linkai") and conf().get("linkai_api_key"):
                self.btype["chat"] = const.LINKAI
                if not conf().get("voice_to_text") or conf().get("voice_to_text") in ["openai"]:
                    self.btype["voice_to_text"] = const.LINKAI
                if not conf().get("text_to_voice") or conf().get("text_to_voice") in ["openai", const.TTS_1, const.TTS_1_HD]:
                    self.btype["text_to_voice"] = const.LINKAI

        self.bots = {}
        self.chat_bots = {}

    # 模型对应的接口
    def get_bot(self, typename):
        if self.bots.get(typename) is None:
            logger.info("create bot {} for {}".format(self.btype[typename], typename))
            if typename == "text_to_voice":
                self.bots[typename] = create_voice(self.btype[typename])
            elif typename == "voice_to_text":
                self.bots[typename] = create_voice(self.btype[typename])
            elif typename == "chat":
                self.bots[typename] = create_bot(self.btype[typename])
            elif typename == "translate":
                self.bots[typename] = create_translator(self.btype[typename])
        return self.bots[typename]

    def get_bot_type(self, typename):
        return self.btype[typename]

    def fetch_reply_content(self, query, context: Context) -> Reply:
        model_config = context.get("model_config")
        stream_enabled = context.get("stream_enabled", False)
        
        if model_config:
            # 动态模式：根据请求配置创建Bot
            logger.info(f"[Bridge] Using dynamic mode with model: {model_config.get('model')}, stream: {stream_enabled}")
            bot = self.create_dynamic_bot(model_config)
            
            if stream_enabled:
                # 流式模式：处理生成器响应
                return self._handle_stream_response(bot, query, context)
            else:
                # 非流式模式：直接返回完整响应
                return bot.reply(query, context)
        else:
            # 兼容模式：使用原有逻辑
            logger.debug("[Bridge] Using legacy mode with default config")
            return self.get_bot("chat").reply(query, context)

    def _handle_stream_response(self, bot, query, context: Context) -> Reply:
        """
        处理流式响应
        
        Args:
            bot: Bot实例
            query: 查询内容
            context: 上下文
            
        Returns:
            Reply对象（用于兼容性，内容可能为空）
        """
        try:
            # 获取Channel实例（用于发送流式数据）
            channel = context.get("channel")
            if not channel:
                logger.error("[Bridge] No channel found in context for streaming")
                # 降级到非流式模式
                return bot.reply(query, context)
            
            logger.info(f"[Bridge] Starting stream processing for request {context.get('request_id')}")
            
            # 调用Bot的流式方法
            stream_generator = bot.reply_stream(query, context)
            
            if stream_generator is None:
                logger.warning("[Bridge] Bot does not support streaming, falling back to regular mode")
                return bot.reply(query, context)
            
            # 处理流式数据
            accumulated_content = ""
            token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            
            for chunk in stream_generator:
                if isinstance(chunk, dict):
                    # 处理数据块
                    chunk_content = chunk.get("content", "")
                    if chunk_content:
                        accumulated_content += chunk_content
                        
                        # 发送数据块到前端
                        chunk_data = {
                            "content": chunk_content,
                            "accumulated_content": accumulated_content,
                            "finished": False,
                            "event": "chunk"
                        }
                        channel.send_chunk(chunk_data, context)
                    
                    # 更新token使用情况
                    if "token_usage" in chunk:
                        token_usage.update(chunk["token_usage"])
                
                elif isinstance(chunk, str):
                    # 简单文本块
                    accumulated_content += chunk
                    chunk_data = {
                        "content": chunk,
                        "accumulated_content": accumulated_content,
                        "finished": False,
                        "event": "chunk"
                    }
                    channel.send_chunk(chunk_data, context)
            
            # 发送结束信号
            final_data = {
                "content": accumulated_content,
                "token_usage": token_usage,
                "accumulated_content": accumulated_content
            }
            channel.send_stream_end(context, final_data)
            
            logger.info(f"[Bridge] Stream processing completed for request {context.get('request_id')}")
            
            # 返回一个Reply对象用于兼容性（虽然内容已经通过流发送）
            from bridge.reply import Reply, ReplyType
            reply = Reply(ReplyType.TEXT, accumulated_content)
            reply.token_usage = token_usage
            return reply
            
        except Exception as e:
            logger.error(f"[Bridge] Error in stream processing: {e}")
            # 发送错误信息
            if channel:
                error_data = {
                    "error": str(e),
                    "finished": True,
                    "event": "error"
                }
                channel.send_chunk(error_data, context)
            
            # 返回错误Reply
            from bridge.reply import Reply, ReplyType
            return Reply(ReplyType.ERROR, f"Stream processing failed: {str(e)}")

    def create_dynamic_bot(self, model_config):
        """根据模型配置动态创建Bot实例"""
        model_name = model_config.get("model", "").lower()
        
        # if "gpt" in model_name or "o1" in model_name or model_name.startswith("chatgpt"):
        #     from bot.openai.dynamic_openai_bot import DynamicOpenAIBot
        #     return DynamicOpenAIBot(model_config)
        # elif "gemini" in model_name:
        #     from bot.gemini.dynamic_gemini_bot import DynamicGeminiBot
        #     return DynamicGeminiBot(model_config)
        # elif "claude" in model_name:
        #     from bot.claude.dynamic_claude_bot import DynamicClaudeBot
        #     return DynamicClaudeBot(model_config)
        # else:
        #     # 默认使用OpenAI兼容格式
        #     logger.warning(f"[Bridge] Unknown model {model_name}, using OpenAI compatible format")
        #     from bot.openai.dynamic_openai_bot import DynamicOpenAIBot
        #     return DynamicOpenAIBot(model_config)
        
        #现在默认使用统一的openai接口规范调用
        logger.warning(f"[Bridge] Unknown model {model_name}, using OpenAI compatible format")
        from bot.openai.dynamic_openai_bot import DynamicOpenAIBot
        return DynamicOpenAIBot(model_config)

    def fetch_voice_to_text(self, voiceFile) -> Reply:
        return self.get_bot("voice_to_text").voiceToText(voiceFile)

    def fetch_text_to_voice(self, text) -> Reply:
        return self.get_bot("text_to_voice").textToVoice(text)

    def fetch_translate(self, text, from_lang="", to_lang="en") -> Reply:
        return self.get_bot("translate").translate(text, from_lang, to_lang)

    def find_chat_bot(self, bot_type: str):
        if self.chat_bots.get(bot_type) is None:
            self.chat_bots[bot_type] = create_bot(bot_type)
        return self.chat_bots.get(bot_type)

    def reset_bot(self):
        """
        重置bot路由
        """
        self.__init__()
