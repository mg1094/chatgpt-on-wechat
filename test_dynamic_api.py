#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试动态API的脚本 - 支持多轮对话和角色扮演
"""

import requests
import json
import time

def load_character_data():
    """加载角色数据"""
    try:
        with open('bot/prompt/Wyatt.json', 'r', encoding='utf-8') as f:
            wyatt_data = json.load(f)
        return wyatt_data
    except Exception as e:
        print(f"❌ 加载角色文件失败: {e}")
        return None

def build_system_prompt():
    """构建系统提示词 - 完整拼接prompt.py和JSON内容"""
    
    # 读取完整的prompt.py文件内容
    try:
        with open('bot/prompt/prompt.py', 'r', encoding='utf-8') as f:
            prompt_content = f.read()
        
        # 提取prompt变量的内容（去除 prompt = """ 和 """）
        import re
        prompt_match = re.search(r'prompt\s*=\s*"""(.*?)"""', prompt_content, re.DOTALL)
        if prompt_match:
            role_play_prompt = prompt_match.group(1).strip()
        else:
            role_play_prompt = "默认角色扮演提示词"
            
    except Exception as e:
        print(f"⚠️  读取prompt.py失败: {e}")
        role_play_prompt = "默认角色扮演提示词"
    
    # 加载完整的角色JSON数据
    wyatt_data = load_character_data()
    if not wyatt_data:
        return role_play_prompt
    
    # 将完整JSON转换为字符串
    wyatt_json_str = json.dumps(wyatt_data, indent=2, ensure_ascii=False)
    
    # 完整拼接：prompt.py内容 + JSON内容
    system_prompt = f"""{role_play_prompt}

## 完整角色JSON数据
以下是角色Wyatt的完整JSON配置信息：

```json
{wyatt_json_str}
```

现在开始根据以上提示词和角色JSON信息，扮演Wyatt这个角色，与用户进行对话。"""
    
    return system_prompt

def interactive_chat():
    """交互式聊天"""
    url = "http://localhost:9899/message"
    poll_url = "http://localhost:9899/poll"
    
    # 生成唯一会话ID
    session_id = f"wyatt_test_{int(time.time())}"
    
    # 构建系统提示
    system_prompt = build_system_prompt()
    
    # 初始化消息历史
    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]
    
    print("🏄‍♂️ Wyatt角色扮演聊天已启动!")
    print("💬 您可以开始与Wyatt对话了")
    print("🚪 输入 'quit', 'exit' 或 'q' 退出聊天")
    print("="*60)
    
    while True:
        try:
            # 获取用户输入
            user_input = input("\n👤 你: ").strip()
            
            # 检查退出命令
            if user_input.lower() in ['quit', 'exit', 'q', '退出']:
                print("\n👋 再见! 聊天已结束。")
                break
            
            if not user_input:
                print("⚠️  请输入内容...")
                continue
            
            # 添加用户消息到历史
            messages.append({
                "role": "user", 
                "content": user_input
            })
            
            # 构建请求数据
            test_data = {
                "session_id": session_id,
                "model": "gemini-2.5-flash-nothink",
                "model_url": "https://aihubmix.com/v1", 
                "api_key": "sk-4thqqoOvnOTWWWHDEbD91389AbC641568eDbEd8cFf83DcDb",
                "messages": messages.copy()
            }
            
            print(f"\n📤 发送消息...")
            
            # 发送POST请求
            response = requests.post(url, json=test_data, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                request_id = result.get("request_id")
                
                if request_id:
                    # 轮询获取响应
                    poll_data = {"session_id": session_id}
                    
                    print("⏳ 等待Wyatt回复...")
                    for i in range(60):  # 最多轮询60秒
                        time.sleep(1)
                        poll_response = requests.post(poll_url, json=poll_data, timeout=5)
                        if poll_response.status_code == 200:
                            poll_result = poll_response.json()
                            if poll_result.get("has_content"):
                                ai_response = poll_result.get('content')
                                token_usage = poll_result.get('token_usage')
                                
                                print(f"\n🏄‍♂️ Wyatt: {ai_response}")
                                
                                if token_usage:
                                    print(f"📊 Token使用: {token_usage}")
                                
                                # 将AI回复添加到历史
                                messages.append({
                                    "role": "assistant",
                                    "content": ai_response
                                })
                                break
                        else:
                            print(f"轮询失败: {poll_response.status_code}")
                            break
                    else:
                        print("\n⏰ 响应超时，请重试...")
                else:
                    print("❌ 未获取到请求ID")
            else:
                print(f"❌ 请求失败: {response.status_code} - {response.text}")
                
        except KeyboardInterrupt:
            print("\n\n🛑 用户中断聊天")
            break
        except Exception as e:
            print(f"\n❌ 请求异常: {e}")
            print("🔄 请重试...")

def test_new_format():
    """测试新的API格式"""
    url = "http://localhost:9899/message"
    
    # 测试数据
    test_data = {
        "session_id": "simple_test",
        "model": "gemini-2.5-flash-nothink",
        "model_url": "https://aihubmix.com/v1", 
        "api_key": "sk-4thqqoOvnOTWWWHDEbD91389AbC641568eDbEd8cFf83DcDb",
        "messages": [
            {
                "role": "system",
                "content": "你是一个温柔体贴、善于倾听的虚拟伴侣，名叫'小暖'。"
            },
            {
                "role": "user",
                "content": "我今天心情很低落。"
            }
        ]
    }
    
    print("发送测试请求...")
    print(f"URL: {url}")
    print(f"Data: {json.dumps(test_data, indent=2, ensure_ascii=False)}")
    
    try:
        # 发送POST请求
        response = requests.post(url, json=test_data, timeout=10)
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            request_id = result.get("request_id")
            print(f"请求ID: {request_id}")
            
            if request_id:
                # 轮询获取响应
                poll_url = "http://localhost:9899/poll"
                poll_data = {"session_id": test_data["session_id"]}
                
                print("\n开始轮询响应...")
                for i in range(30):  # 最多轮询30次
                    time.sleep(1)
                    poll_response = requests.post(poll_url, json=poll_data, timeout=5)
                    if poll_response.status_code == 200:
                        poll_result = poll_response.json()
                        if poll_result.get("has_content"):
                            print("\n✅ 获取到响应:")
                            print(f"内容: {poll_result.get('content')}")
                            print(f"请求ID: {poll_result.get('request_id')}")
                            return True
                        else:
                            print(f"第{i+1}次轮询: 暂无内容")
                    else:
                        print(f"轮询失败: {poll_response.status_code}")
                
                print("\n❌ 轮询超时，未获取到响应")
                return False
        else:
            print(f"❌ 请求失败: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return False

def test_legacy_format():
    """测试旧的API格式（兼容性测试）"""
    url = "http://localhost:9899/message"
    
    # 旧格式测试数据
    test_data = {
        "session_id": "legacy_test_session",
        "message": "你好，这是兼容性测试"
    }
    
    print("\n" + "="*50)
    print("测试旧格式兼容性...")
    print(f"Data: {json.dumps(test_data, indent=2, ensure_ascii=False)}")
    
    try:
        response = requests.post(url, json=test_data, timeout=10)
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 旧格式兼容性测试通过")
            return True
        else:
            print("❌ 旧格式兼容性测试失败")
            return False
            
    except Exception as e:
        print(f"❌ 旧格式测试异常: {e}")
        return False

if __name__ == "__main__":
    print("="*60)
    print("🚀 动态API测试工具")
    print("="*60)
    print("1. 交互式角色扮演聊天 (Wyatt)")
    print("2. 简单API格式测试")
    print("3. 旧格式兼容性测试")
    print("="*60)
    
    while True:
        try:
            choice = input("\n请选择测试模式 (1/2/3) 或输入 'q' 退出: ").strip()
            
            if choice.lower() == 'q':
                print("👋 再见！")
                break
            elif choice == '1':
                print("\n🎭 启动Wyatt角色扮演聊天...")
                interactive_chat()
            elif choice == '2':
                print("\n🧪 测试简单API格式...")
                success = test_new_format()
                print(f"测试结果: {'✅ 通过' if success else '❌ 失败'}")
            elif choice == '3':
                print("\n🔄 测试旧格式兼容性...")
                success = test_legacy_format()
                print(f"测试结果: {'✅ 通过' if success else '❌ 失败'}")
            else:
                print("⚠️  请输入有效选项 (1/2/3/q)")
                
        except KeyboardInterrupt:
            print("\n\n👋 程序已退出")
            break
        except Exception as e:
            print(f"\n❌ 发生错误: {e}")
            print("🔄 请重试...") 