# encoding:utf-8

import time

import openai
import openai.error

from bot.bot import Bot
from bot.openai.open_ai_image import OpenAIImage
from bot.openai.open_ai_session import OpenAISession
from bot.session_manager import SessionManager
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from config import conf

user_session = dict()


# OpenAI对话模型API (可用)
class OpenAIBot(Bot, OpenAIImage):
    def __init__(self):
        super().__init__()
        openai.api_key = conf().get("open_ai_api_key")    
        if conf().get("open_ai_api_base"):
            openai.api_base = conf().get("open_ai_api_base")
        proxy = conf().get("proxy")
        if proxy:
            openai.proxy = proxy

        self.sessions = SessionManager(OpenAISession, model=conf().get("model") or "gpt-3.5-turbo")
        self.args = {
            "model": conf().get("model") or "gpt-3.5-turbo",  # 对话模型的名称
            "temperature": conf().get("temperature", 0.9),  # 值在[0,1]之间，越大表示回复越具有不确定性
            "max_tokens": 1200,  # 回复最大的字符数
            "top_p": 1,
            "frequency_penalty": conf().get("frequency_penalty", 0.0),  # [-2,2]之间，该值越大则更倾向于产生不同的内容
            "presence_penalty": conf().get("presence_penalty", 0.0),  # [-2,2]之间，该值越大则更倾向于产生不同的内容
            "request_timeout": conf().get("request_timeout", None),  # 请求超时时间，openai接口默认设置为600，对于难问题一般需要较长时间
            "timeout": conf().get("request_timeout", None),  # 重试超时时间，在这个时间内，将会自动重试
        }

    def reply(self, query, context=None):
        # acquire reply content
        if context and context.type:
            if context.type == ContextType.TEXT:
                logger.info("[OPEN_AI] query={}".format(query))
                session_id = context["session_id"]
                reply = None
                if query == "#清除记忆":
                    self.sessions.clear_session(session_id)
                    reply = Reply(ReplyType.INFO, "记忆已清除")
                elif query == "#清除所有":
                    self.sessions.clear_all_session()
                    reply = Reply(ReplyType.INFO, "所有人记忆已清除")
                else:
                    session = self.sessions.session_query(query, session_id)
                    result = self.reply_text(session)
                    if result.get("total_tokens", 0) == 0:
                        reply = Reply(ReplyType.ERROR, result["content"])
                    else:
                        reply_content = result["content"]
                        token_usage = {
                            "prompt_tokens": result.get("input_tokens", 0),
                            "completion_tokens": result.get("completion_tokens", 0),
                            "total_tokens": result.get("total_tokens", 0),
                        }
                        
                        # 记录日志和会话
                        logger.debug(
                            "[OPEN_AI] new_query={}, session_id={}, reply_cont={}, completion_tokens={}".format(
                                str(session), session_id, reply_content, token_usage["completion_tokens"]
                            )
                        )
                        self.sessions.session_reply(reply_content, session_id, token_usage["total_tokens"])
                        reply = Reply(ReplyType.TEXT, reply_content, token_usage)
                return reply
            elif context.type == ContextType.IMAGE_CREATE:
                ok, retstring = self.create_img(query, 0)
                reply = None
                if ok:
                    reply = Reply(ReplyType.IMAGE_URL, retstring)
                else:
                    reply = Reply(ReplyType.ERROR, retstring)
                return reply

    def _convert_session_to_messages(self, session: OpenAISession):
        """将OpenAISession转换为ChatCompletion所需的messages格式"""
        messages = []
        
        # 添加系统消息（如果有的话）
        if hasattr(session, 'system_prompt') and session.system_prompt:
            messages.append({"role": "system", "content": session.system_prompt})
        
        # 将session的历史消息转换为messages格式
        # 假设session.messages是一个包含历史对话的列表
        if hasattr(session, 'messages') and session.messages:
            for msg in session.messages:
                if isinstance(msg, dict):
                    # 如果已经是字典格式，直接添加
                    messages.append(msg)
                else:
                    # 如果是字符串格式，需要解析
                    # 这里需要根据OpenAISession的实际格式来调整
                    messages.append({"role": "user", "content": str(msg)})
        else:
            # 如果没有历史消息，将整个session作为用户消息
            session_str = str(session)
            if session_str.strip():
                messages.append({"role": "user", "content": session_str})
        
        return messages

    def reply_text(self, session: OpenAISession, retry_count=0):
        try:
            # 将session转换为messages格式
            messages = self._convert_session_to_messages(session)
            
            response = openai.ChatCompletion.create(messages=messages, **self.args)
            res_content = response.choices[0]["message"]["content"].strip()
            total_tokens = response["usage"]["total_tokens"]
            completion_tokens = response["usage"]["completion_tokens"]
            prompt_tokens = response["usage"]["prompt_tokens"]
            logger.info("[OPEN_AI] reply={}".format(res_content))
            return {
                "total_tokens": total_tokens,
                "completion_tokens": completion_tokens,
                "input_tokens": prompt_tokens,
                "content": res_content,
            }
        except Exception as e:
            need_retry = retry_count < 2
            result = {"completion_tokens": 0, "content": "我现在有点累了，等会再来吧"}
            if isinstance(e, openai.error.RateLimitError):
                logger.warn("[OPEN_AI] RateLimitError: {}".format(e))
                result["content"] = "提问太快啦，请休息一下再问我吧"
                if need_retry:
                    time.sleep(20)
            elif isinstance(e, openai.error.Timeout):
                logger.warn("[OPEN_AI] Timeout: {}".format(e))
                result["content"] = "我没有收到你的消息"
                if need_retry:
                    time.sleep(5)
            elif isinstance(e, openai.error.APIConnectionError):
                logger.warn("[OPEN_AI] APIConnectionError: {}".format(e))
                need_retry = False
                result["content"] = "我连接不到你的网络"
            else:
                logger.warn("[OPEN_AI] Exception: {}".format(e))
                need_retry = False
                self.sessions.clear_session(session.session_id)

            if need_retry:
                logger.warn("[OPEN_AI] 第{}次重试".format(retry_count + 1))
                return self.reply_text(session, retry_count + 1)
            else:
                return result
