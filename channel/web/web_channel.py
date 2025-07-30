import sys
import time
import web
import json
import uuid
from queue import Queue, Empty
from bridge.context import *
from bridge.reply import Reply, ReplyType
from channel.chat_channel import ChatChannel, check_prefix
from channel.chat_message import ChatMessage
from common.log import logger
from common.singleton import singleton
from config import conf
from bot.prompt.prompt_processor import PromptProcessor
import os
import mimetypes  # 添加这行来处理MIME类型
import threading
import logging

class WebMessage(ChatMessage):
    def __init__(
        self,
        msg_id,
        content,
        ctype=ContextType.TEXT,
        from_user_id="User",
        to_user_id="Chatgpt",
        other_user_id="Chatgpt",
    ):
        self.msg_id = msg_id
        self.ctype = ctype
        self.content = content
        self.from_user_id = from_user_id
        self.to_user_id = to_user_id
        self.other_user_id = other_user_id


@singleton
class WebChannel(ChatChannel):
    NOT_SUPPORT_REPLYTYPE = [ReplyType.VOICE]
    _instance = None
    
    # def __new__(cls):
    #     if cls._instance is None:
    #         cls._instance = super(WebChannel, cls).__new__(cls)
    #     return cls._instance

    def __init__(self):
        super().__init__()
        self.msg_id_counter = 0  # 添加消息ID计数器
        self.session_queues = {}  # 存储session_id到队列的映射
        self.stream_queues = {}  # 存储request_id到流式数据队列的映射
        self.prompt_processor = PromptProcessor()  # 初始化提示词处理器
        self.request_to_session = {}  # 存储request_id到session_id的映射
        # web channel无需前缀
        conf()["single_chat_prefix"] = [""]


    def _generate_msg_id(self):
        """生成唯一的消息ID"""
        self.msg_id_counter += 1
        return str(int(time.time())) + str(self.msg_id_counter)

    def _generate_request_id(self):
        """生成唯一的请求ID"""
        return str(uuid.uuid4())

    def _extract_latest_user_message(self, messages):
        """从messages列表中提取最新的用户消息"""
        if not messages:
            return ""
        
        # 从后往前找最新的user消息
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", "")
        
        return ""

    def send(self, reply: Reply, context: Context):
        try:
            if reply.type in self.NOT_SUPPORT_REPLYTYPE:
                logger.warning(f"Web channel doesn't support {reply.type} yet")
                return

            if reply.type == ReplyType.IMAGE_URL:
                time.sleep(0.5)

            # 获取请求ID和会话ID
            request_id = context.get("request_id", None)
            
            if not request_id:
                logger.error("No request_id found in context, cannot send message")
                return
                
            # 通过request_id获取session_id
            session_id = self.request_to_session.get(request_id)
            if not session_id:
                logger.error(f"No session_id found for request {request_id}")
                return
            
            # 检查是否有会话队列
            if session_id in self.session_queues:
                # 创建响应数据，包含请求ID以区分不同请求的响应
                response_data = {
                    "type": str(reply.type),
                    "content": reply.content,
                    "token_usage": reply.token_usage,
                    "timestamp": time.time(),
                    "request_id":request_id,
                    "session_id": session_id
                }
                self.session_queues[session_id].put(response_data)
                logger.debug(f"Response sent to queue for session {session_id}, request {request_id}")
            else:
                logger.warning(f"No response queue found for session {session_id}, response dropped")
            
        except Exception as e:
            logger.error(f"Error in send method: {e}")

    def send_chunk(self, chunk_data: dict, context: Context):
        """
        发送流式数据块到前端
        
        Args:
            chunk_data: 包含流式数据的字典，如 {"content": "hello", "finished": False}
            context: 上下文对象，包含request_id
        """
        try:
            request_id = context.get("request_id", None)
            if not request_id:
                logger.error("No request_id found in context, cannot send chunk")
                return
            
            # 确保流队列存在
            if request_id not in self.stream_queues:
                self.stream_queues[request_id] = Queue()
                logger.debug(f"Created stream queue for request {request_id}")
            
            # 添加时间戳和请求ID
            chunk_data["timestamp"] = time.time()
            chunk_data["request_id"] = request_id
            
            # 将数据块放入流队列
            self.stream_queues[request_id].put(chunk_data)
            logger.debug(f"Chunk sent to stream queue for request {request_id}: {chunk_data.get('content', '')[:50]}...")
            
        except Exception as e:
            logger.error(f"Error in send_chunk method: {e}")

    def send_stream_end(self, context: Context, final_data: dict = None):
        """
        发送流结束信号
        
        Args:
            context: 上下文对象
            final_data: 最终数据，如token使用情况
        """
        try:
            request_id = context.get("request_id", None)
            if not request_id:
                logger.error("No request_id found in context, cannot send stream end")
                return
            
            # 构建结束信号
            end_signal = {
                "event": "end",
                "timestamp": time.time(),
                "request_id": request_id,
                "finished": True
            }
            
            # 添加最终数据（如token使用情况）
            if final_data:
                end_signal.update(final_data)
            
            # 发送结束信号
            if request_id in self.stream_queues:
                self.stream_queues[request_id].put(end_signal)
                logger.debug(f"Stream end signal sent for request {request_id}")
            
        except Exception as e:
            logger.error(f"Error in send_stream_end method: {e}")

    def post_message(self):
        """
        Handle incoming messages from users via POST request.
        Returns a request_id for tracking this specific request.
        """
        try:
            data = web.data()  # 获取原始POST数据
            json_data = json.loads(data)
            
            # 检测输入格式并解析
            if 'messages' in json_data:
                # 新格式：完整配置
                session_id = json_data.get('session_id', f'session_{int(time.time())}')
                original_messages = json_data.get('messages', [])
                stream_enabled = json_data.get('stream', False)
                
                # 应用提示词处理管道
                processed_messages = self.prompt_processor.process_full_pipeline(original_messages)
                logger.info(f"[WebChannel] 处理后的messages: {json.dumps(processed_messages, ensure_ascii=False, indent=2)}")
                
                model_config = {
                    'model': json_data.get('model'),
                    'model_url': json_data.get('model_url'),
                    'api_key': json_data.get('api_key'),
                    'messages': processed_messages,  # 使用处理后的messages
                    'stream': stream_enabled
                }
                # 从messages中提取最新的user消息作为prompt
                prompt = self._extract_latest_user_message(processed_messages)
                logger.info(f"[WebChannel] New format request processed: model={model_config['model']}, session_id={session_id}, messages_count={len(processed_messages)}, stream={stream_enabled}")
            else:
                # 旧格式：兼容处理
                session_id = json_data.get('session_id', f'session_{int(time.time())}')
                prompt = json_data.get('message', '')
                stream_enabled = False  # 旧格式不支持流式
                model_config = None  # 使用后端默认配置
                logger.info(f"[WebChannel] Legacy format request: session_id={session_id}")
            
            # 生成请求ID
            request_id = self._generate_request_id()
            
            # 将请求ID与会话ID关联
            self.request_to_session[request_id] = session_id
            
            # 确保会话队列存在（非流式模式需要）
            if session_id not in self.session_queues:
                self.session_queues[session_id] = Queue()
            
            # 为流式请求创建流队列
            if stream_enabled:
                self.stream_queues[request_id] = Queue()
                logger.debug(f"Created stream queue for request {request_id}")
            
            # 创建消息对象
            msg = WebMessage(self._generate_msg_id(), prompt)
            msg.from_user_id = session_id  # 使用会话ID作为用户ID
            
            # 创建上下文
            context = self._compose_context(ContextType.TEXT, prompt, msg=msg)

            # 添加必要的字段
            context["session_id"] = session_id
            context["request_id"] = request_id
            context["isgroup"] = False  # 添加 isgroup 字段
            context["receiver"] = session_id  # 添加 receiver 字段
            context["model_config"] = model_config  # 添加模型配置
            context["stream_enabled"] = stream_enabled  # 添加流式标识
            
            # 异步处理消息 - 只传递上下文
            threading.Thread(target=self.produce, args=(context,), daemon=True).start()
            
            # 构建响应
            response = {
                "status": "success", 
                "session_id": session_id, 
                "request_id": request_id
            }
            
            # 如果启用了流式，添加stream_url
            if stream_enabled:
                response["stream_url"] = f"/stream/{request_id}"
                logger.debug(f"Stream URL generated: /stream/{request_id}")
            
            return json.dumps(response)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return json.dumps({"status": "error", "message": str(e)})

    def poll_response(self):
        """
        Poll for responses using the session_id.
        """
        try:
            # 不记录轮询请求的日志
            web.ctx.log_request = False
            
            data = web.data()
            json_data = json.loads(data)
            session_id = json_data.get('session_id')
            
            if not session_id or session_id not in self.session_queues:
                return json.dumps({"status": "error", "message": "Invalid session ID"})
            
            # 尝试从队列获取响应，不等待
            try:
                # 使用peek而不是get，这样如果前端没有成功处理，下次还能获取到
                response = self.session_queues[session_id].get(block=False)
                
                # 返回响应，包含请求ID以区分不同请求
                return json.dumps({
                    "status": "success" if response["type"] != "ERROR" else False, 
                    "has_content": True if response["type"] != "ERROR" else False,
                    "content": response["content"],
                    "token_usage": response["token_usage"],
                    "session_id": response["session_id"],
                    "request_id": response["request_id"],
                    "timestamp": response["timestamp"]
                })
                
            except Empty:
                # 没有新响应
                return json.dumps({"status": "success", "has_content": False})
                
        except Exception as e:
            logger.error(f"Error polling response: {e}")
            return json.dumps({"status": "false", "message": str(e)})

    def stream_response(self, request_id):
        """
        处理SSE流式响应
        
        Args:
            request_id: 请求ID
        """
        try:
            # 设置SSE响应头
            web.header('Content-Type', 'text/event-stream; charset=utf-8')
            web.header('Cache-Control', 'no-cache')
            web.header('Connection', 'keep-alive')
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Access-Control-Allow-Headers', 'Cache-Control')
            
            # 检查流队列是否存在
            if request_id not in self.stream_queues:
                logger.warning(f"Stream queue not found for request {request_id}")
                yield f"data: {json.dumps({'error': 'Stream not found'}, ensure_ascii=False)}\n\n"
                return
            
            logger.info(f"Starting SSE stream for request {request_id}")
            
            # 发送初始连接确认
            yield f"data: {json.dumps({'event': 'connected', 'request_id': request_id}, ensure_ascii=False)}\n\n"
            
            # 持续从流队列获取数据
            stream_queue = self.stream_queues[request_id]
            timeout = 30  # 30秒超时
            
            while True:
                try:
                    # 从队列获取数据，设置超时
                    chunk_data = stream_queue.get(timeout=timeout)
                    
                    # 构建SSE消息，确保正确处理特殊字符
                    event_data = json.dumps(chunk_data, ensure_ascii=False, separators=(',', ':'))
                    
                    # 对于包含换行符的内容，需要进行适当的转义
                    # 但JSON.dumps已经处理了转义，所以这里直接使用
                    yield f"data: {event_data}\n\n"
                    
                    # 检查是否为结束信号
                    if chunk_data.get("event") == "end" or chunk_data.get("finished", False):
                        logger.info(f"Stream ended for request {request_id}")
                        break
                        
                except Empty:
                    # 超时，发送心跳
                    logger.debug(f"Stream timeout for request {request_id}, sending heartbeat")
                    yield f"data: {json.dumps({'event': 'heartbeat', 'timestamp': time.time()}, ensure_ascii=False)}\n\n"
                    
                except Exception as e:
                    logger.error(f"Error in stream loop for request {request_id}: {e}")
                    yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
                    break
            
            # 清理流队列
            if request_id in self.stream_queues:
                del self.stream_queues[request_id]
                logger.debug(f"Cleaned up stream queue for request {request_id}")
                
        except Exception as e:
            logger.error(f"Error in stream_response for request {request_id}: {e}")
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    def chat_page(self):
        """Serve the chat HTML page."""
        file_path = os.path.join(os.path.dirname(__file__), 'chat.html')  # 使用绝对路径
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def startup(self):
        port = conf().get("web_port", 9899)
        logger.info("""[WebChannel] 当前channel为web，可修改 config.json 配置文件中的 channel_type 字段进行切换。全部可用类型为：
        1. web: 网页
        2. terminal: 终端
        3. wechatmp: 个人公众号
        4. wechatmp_service: 企业公众号
        5. wechatcom_app: 企微自建应用
        6. dingtalk: 钉钉
        7. feishu: 飞书""")
        logger.info(f"Web对话网页已运行, 请使用浏览器访问 http://localhost:{port}/chat（本地运行）或 http://ip:{port}/chat（服务器运行） ")
        
        # 确保静态文件目录存在
        static_dir = os.path.join(os.path.dirname(__file__), 'static')
        if not os.path.exists(static_dir):
            os.makedirs(static_dir)
            logger.info(f"Created static directory: {static_dir}")
        
        urls = (
            '/', 'RootHandler',  # 添加根路径处理器
            '/message', 'MessageHandler',
            '/poll', 'PollHandler',  # 添加轮询处理器
            '/chat', 'ChatHandler',
            '/stream/(.*)', 'StreamHandler',  # 添加流式处理器
            '/assets/(.*)', 'AssetsHandler',  # 匹配 /assets/任何路径
        )
        app = web.application(urls, globals(), autoreload=False)
        
        # 禁用web.py的默认日志输出
        import io
        from contextlib import redirect_stdout
        
        # 配置web.py的日志级别为ERROR，只显示错误
        logging.getLogger("web").setLevel(logging.ERROR)
        
        # 禁用web.httpserver的日志
        logging.getLogger("web.httpserver").setLevel(logging.ERROR)
        
        # 临时重定向标准输出，捕获web.py的启动消息
        with redirect_stdout(io.StringIO()):
            web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", port))


class RootHandler:
    def GET(self):
        # 重定向到/chat
        raise web.seeother('/chat')


class MessageHandler:
    def POST(self):
        return WebChannel().post_message()


class PollHandler:
    def POST(self):
        return WebChannel().poll_response()


class StreamHandler:
    def GET(self, request_id):
        """处理SSE流式响应"""
        try:
            if not request_id:
                raise web.badrequest("Missing request_id")
            
            # 获取WebChannel实例并调用stream_response方法
            web_channel = WebChannel()
            
            # 返回生成器用于SSE流式响应
            return web_channel.stream_response(request_id)
            
        except Exception as e:
            logger.error(f"Error in StreamHandler: {e}")
            web.header('Content-Type', 'application/json')
            return json.dumps({"error": str(e)})


class ChatHandler:
    def GET(self):
        # 正常返回聊天页面
        file_path = os.path.join(os.path.dirname(__file__), 'chat.html')
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()


class AssetsHandler:
    def GET(self, file_path):  # 修改默认参数
        try:
            # 如果请求是/static/，需要处理
            if file_path == '':
                # 返回目录列表...
                pass

            # 获取当前文件的绝对路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            static_dir = os.path.join(current_dir, 'static')

            full_path = os.path.normpath(os.path.join(static_dir, file_path))

            # 安全检查：确保请求的文件在static目录内
            if not os.path.abspath(full_path).startswith(os.path.abspath(static_dir)):
                logger.error(f"Security check failed for path: {full_path}")
                raise web.notfound()

            if not os.path.exists(full_path) or not os.path.isfile(full_path):
                logger.error(f"File not found: {full_path}")
                raise web.notfound()

            # 设置正确的Content-Type
            content_type = mimetypes.guess_type(full_path)[0]
            if content_type:
                web.header('Content-Type', content_type)
            else:
                # 默认为二进制流
                web.header('Content-Type', 'application/octet-stream')

            # 读取并返回文件内容
            with open(full_path, 'rb') as f:
                return f.read()

        except Exception as e:
            logger.error(f"Error serving static file: {e}", exc_info=True)  # 添加更详细的错误信息
            raise web.notfound()
