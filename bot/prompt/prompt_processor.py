import json
import os
import re
import hashlib
from typing import Dict, List, Any, Optional
from common.log import logger


class PromptProcessor:
    """
    提示词处理器 - 负责角色JSON数据清洗、提示词合并和messages重构
    """
    
    def __init__(self):
        self._base_prompt_cache = {}
        self._cleaned_char_cache = {}
    
    def clean_character_data(self, raw_char_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        清洗角色JSON数据，去除重复属性，保留有效值
        
        Args:
            raw_char_json: 原始角色JSON数据
            
        Returns:
            清洗后的角色数据
        """
        if not isinstance(raw_char_json, dict):
            logger.warning("[PromptProcessor] Invalid character data format, using as-is")
            return raw_char_json
        
        # 创建内容hash用于缓存
        content_hash = hashlib.md5(json.dumps(raw_char_json, sort_keys=True).encode()).hexdigest()
        if content_hash in self._cleaned_char_cache:
            logger.debug("[PromptProcessor] Using cached cleaned character data")
            return self._cleaned_char_cache[content_hash]
        
        logger.info("[PromptProcessor] Starting character data cleaning")
        cleaned_char = {}
        
        # 步骤1: 优先处理嵌套的data对象
        if 'data' in raw_char_json and isinstance(raw_char_json['data'], dict):
            logger.debug("[PromptProcessor] Processing nested 'data' object first")
            cleaned_char.update(raw_char_json['data'])
        
        # 步骤2: 合并顶层属性，应用优先级规则
        for key, value in raw_char_json.items():
            if key == 'data':  # 跳过data对象本身
                continue
                
            # 规则1: 如果cleaned_char中没有这个键，直接添加
            if key not in cleaned_char:
                cleaned_char[key] = value
                continue
            
            # 规则2: 非空值优先于空值
            if self._is_empty_value(cleaned_char[key]) and not self._is_empty_value(value):
                logger.debug(f"[PromptProcessor] Replacing empty value for key '{key}'")
                cleaned_char[key] = value
                continue
            
            # 规则3: 对于文本类型，较长的内容优先
            if isinstance(value, str) and isinstance(cleaned_char[key], str):
                if len(value.strip()) > len(cleaned_char[key].strip()):
                    logger.debug(f"[PromptProcessor] Using longer text content for key '{key}'")
                    cleaned_char[key] = value
        
        # 步骤3: 字段标准化
        cleaned_char = self._standardize_fields(cleaned_char)
        
        # 步骤4: 移除空值字段
        cleaned_char = self._remove_empty_fields(cleaned_char)
        
        # 缓存结果
        self._cleaned_char_cache[content_hash] = cleaned_char
        logger.info(f"[PromptProcessor] Character data cleaning completed, {len(cleaned_char)} fields retained")
        
        return cleaned_char
    
    def _is_empty_value(self, value: Any) -> bool:
        """判断值是否为空"""
        if value is None:
            return True
        if isinstance(value, str):
            return len(value.strip()) == 0
        if isinstance(value, (list, dict)):
            return len(value) == 0
        return False
    
    def _standardize_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化字段名称和格式"""
        # 字段名映射表
        field_mapping = {
            'creatorcomment': 'creator_notes',
            'mes_example': 'example_dialogue'
        }
        
        standardized = {}
        for key, value in data.items():
            # 应用字段名映射
            standard_key = field_mapping.get(key, key)
            standardized[standard_key] = value
        
        return standardized
    
    def _remove_empty_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """移除空值字段，但保留重要的结构字段"""
        important_fields = {'extensions', 'character_book', 'tags', 'alternate_greetings'}
        
        cleaned = {}
        for key, value in data.items():
            if key in important_fields or not self._is_empty_value(value):
                cleaned[key] = value
        
        return cleaned
    
    def load_base_prompt(self, prompt_file: str = "bot/prompt/prompt-en.py") -> str:
        """
        加载基础提示词文件
        
        Args:
            prompt_file: 提示词文件路径
            
        Returns:
            基础提示词内容
        """
        if prompt_file in self._base_prompt_cache:
            logger.debug("[PromptProcessor] Using cached base prompt")
            return self._base_prompt_cache[prompt_file]
        
        try:
            if not os.path.exists(prompt_file):
                logger.warning(f"[PromptProcessor] Prompt file not found: {prompt_file}, using default")
                return self._get_default_prompt()
            
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取prompt3变量的内容
            prompt_match = re.search(r'prompt3\s*=\s*"""(.*?)"""', content, re.DOTALL)
            if prompt_match:
                base_prompt = prompt_match.group(1).strip()
                logger.info("[PromptProcessor] Successfully loaded base prompt from prompt3 variable")
            else:
                logger.warning("[PromptProcessor] prompt3 variable not found, using file content as-is")
                base_prompt = content
            
            # 缓存结果
            self._base_prompt_cache[prompt_file] = base_prompt
            return base_prompt
            
        except Exception as e:
            logger.error(f"[PromptProcessor] Failed to load prompt file {prompt_file}: {e}")
            return self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        """获取默认提示词模板"""
        return """You are a creative AI assistant for role-playing scenarios. You will accurately portray the character described in the character configuration, maintaining consistency with their personality, speech patterns, and behavior. 

Respond naturally and stay in character throughout the conversation. Focus on creating an engaging and immersive experience for the user."""
    
    def merge_prompts(self, base_prompt: str, cleaned_char: Dict[str, Any]) -> str:
        """
        合并基础提示词和角色数据
        
        Args:
            base_prompt: 基础提示词
            cleaned_char: 清洗后的角色数据
            
        Returns:
            合并后的完整系统提示词
        """
        try:
            # 将角色数据序列化为格式化的JSON
            char_json_str = json.dumps(cleaned_char, indent=2, ensure_ascii=False)
            
            # 按照模板拼接
            merged_prompt = f"""{base_prompt}

Below is the complete JSON configuration information for the character:

```json
{char_json_str}
```

Now begin role-playing as the character based on the provided prompt and character JSON information, engaging in dialogue with the user."""
            
            logger.info("[PromptProcessor] Successfully merged base prompt with character data")
            return merged_prompt
            
        except Exception as e:
            logger.error(f"[PromptProcessor] Failed to merge prompts: {e}")
            return base_prompt  # 降级策略：返回基础提示词
    
    def reconstruct_messages(self, original_messages: List[Dict[str, str]], merged_system_prompt: str) -> List[Dict[str, str]]:
        """
        重构messages列表，替换system消息
        
        Args:
            original_messages: 原始messages列表
            merged_system_prompt: 合并后的系统提示词
            
        Returns:
            重构后的messages列表
        """
        if not isinstance(original_messages, list) or len(original_messages) == 0:
            logger.warning("[PromptProcessor] Empty or invalid messages list")
            return [{"role": "system", "content": merged_system_prompt}]
        
        reconstructed = []
        system_replaced = False
        
        for message in original_messages:
            if not isinstance(message, dict) or 'role' not in message:
                logger.warning(f"[PromptProcessor] Invalid message format: {message}")
                continue
            
            # 替换第一个system消息
            if message['role'] == 'system' and not system_replaced:
                reconstructed.append({
                    "role": "system",
                    "content": merged_system_prompt
                })
                system_replaced = True
                logger.debug("[PromptProcessor] Replaced system message with merged prompt")
            else:
                # 保持其他消息不变
                reconstructed.append(message)
        
        # 如果没有找到system消息，在开头添加一个
        if not system_replaced:
            reconstructed.insert(0, {
                "role": "system", 
                "content": merged_system_prompt
            })
            logger.debug("[PromptProcessor] Added new system message at the beginning")
        
        logger.info(f"[PromptProcessor] Messages reconstruction completed, {len(reconstructed)} messages total")
        return reconstructed
    
    def process_full_pipeline(self, messages: List[Dict[str, str]], prompt_file: str = "bot/prompt/prompt-en.py") -> List[Dict[str, str]]:
        """
        完整的处理管道 - 主入口方法
        
        Args:
            messages: 原始messages列表
            prompt_file: 提示词文件路径
            
        Returns:
            处理后的messages列表
        """
        try:
            logger.info("[PromptProcessor] Starting full processing pipeline")
            
            # 步骤1: 提取角色JSON数据
            char_json_data = self._extract_character_json(messages)
            if not char_json_data:
                logger.info("[PromptProcessor] No character JSON found in system message, using original messages")
                return messages
            
            # 步骤2: 清洗角色数据
            cleaned_char = self.clean_character_data(char_json_data)
            
            # 步骤3: 加载基础提示词
            base_prompt = self.load_base_prompt(prompt_file)
            
            # 步骤4: 合并提示词
            merged_prompt = self.merge_prompts(base_prompt, cleaned_char)
            
            # 步骤5: 重构messages
            final_messages = self.reconstruct_messages(messages, merged_prompt)
            
            logger.info("[PromptProcessor] Full processing pipeline completed successfully")
            return final_messages
            
        except Exception as e:
            logger.error(f"[PromptProcessor] Pipeline processing failed: {e}")
            logger.info("[PromptProcessor] Falling back to original messages")
            return messages  # 降级策略：返回原始messages
    
    def _extract_character_json(self, messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """
        从messages中提取角色JSON数据
        
        Args:
            messages: messages列表
            
        Returns:
            角色JSON数据，如果未找到返回None
        """
        for message in messages:
            if message.get('role') == 'system':
                content = message.get('content', '')
                try:
                    # 尝试直接解析整个content为JSON
                    char_data = json.loads(content)
                    if isinstance(char_data, dict) and 'name' in char_data:
                        logger.debug("[PromptProcessor] Found character JSON in system message")
                        return char_data
                except json.JSONDecodeError:
                    # 尝试从content中提取JSON部分
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        try:
                            char_data = json.loads(json_match.group())
                            if isinstance(char_data, dict) and 'name' in char_data:
                                logger.debug("[PromptProcessor] Extracted character JSON from system message")
                                return char_data
                        except json.JSONDecodeError:
                            continue
        
        logger.debug("[PromptProcessor] No character JSON found in messages")
        return None 