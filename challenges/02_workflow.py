# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "openai",
# ]
# ///

import os
import json
import sys
import time
from openai import OpenAI
import re

# ==========================================
# 配置区域
# ==========================================
# API_KEY = os.getenv("sk-c03c16157366414db39385f6637105b4")
API_KEY="sk-c03c16157366414db39385f6637105b4"
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
# 允许从环境变量覆盖模型名称，默认为 deepseek-chat
MODEL_NAME = os.getenv("DEEPSEEK_MODEL_NAME", "deepseek-chat")

if not API_KEY:
    print("❌ Error: 请设置环境变量 DEEPSEEK_API_KEY")
    sys.exit(1)

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

class LongArticleAgent:
    def __init__(self, topic):
        self.topic = topic
        self.outline = []
        self.articles = []

    def step1_generate_outline(self):
        """Step 1: 生成章节大纲"""
        print(f"📋 正在规划主题: {self.topic}...")

        # TODO: 编写 Prompt 让模型生成纯 JSON 列表
        prompt = (
            f"请为主题《{self.topic}》设计一个长文大纲，规划 14-16 个部分。"
            "要求：\n"
            "1. 输出必须是纯 JSON 格式。\n"
            "2. 结构为一个列表，每个元素包含 'title' (标题) 和 'instruction' (本段落的详细写作指导)。\n"
            "3. 逻辑要连贯，层层递进。"
        )
        
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,  # 使用配置的模型名
                messages=[
                    {"role": "system", "content": "你是一个专业的写作规划师，只输出 JSON Array。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7
            )
            content = response.choices[0].message.content
            
            # TODO: 解析返回的 JSON 内容到 self.outline

            # 兼容 DeepSeek 可能返回的 Markdown 代码块格式
            # -----------------------------------------------------------
            # 清洗 content，防止模型返回 ```json ... ```
            if "```" in content:
                content = re.sub(r"```json|```", "", content).strip()


            data = json.loads(content)
            
            # 简单的容错逻辑示例（候选人需要完善）
            # 兼容性处理：模型可能返回 {"chapters": [...]} 也可能直接返回 [...]
            if isinstance(data, list):
                self.outline = data
            elif isinstance(data, dict):
                # 寻找字典里第一个是 list 的 value
                for key, value in data.items():
                    if isinstance(value, list):
                        self.outline = value
                        break
            
            if not self.outline:
                raise ValueError("未找到有效的大纲列表")

            # print(f"✅ 大纲已生成: {self.outline}")
            print(f"✅ 大纲已生成 (共{len(self.outline)}部分):")

        except Exception as e:
            print(f"❌ 大纲生成失败: {e}")
            print(f"Raw Content: {content if 'content' in locals() else 'None'}")
            sys.exit(1)

    def step2_generate_content_loop(self):
        """Step 2: 循环生成内容，并维护 Context"""
        if not self.outline:
            return

        # 准备全局信息（Global State），让模型知道整体地图，防止跑题
        outline_str = "\n".join([f"{i + 1}. {item.get('title')}" for i, item in enumerate(self.outline)])
        # 初始化上下文摘要
        previous_summary = "文章开始。"
        
        print("\n🚀 开始撰写正文...")
        for i, chapter in enumerate(self.outline):

            title = chapter.get('title')
            instruction = chapter.get('instruction', '撰写本部分内容')

            print(f"[{i+1}/{len(self.outline)}] 正在撰写: {chapter}...")
            
            # TODO: 构造 Prompt，核心在于 Context 的注入
            # prompt = f"""
            # 你是一位专业作家。请撰写章节："{chapter}"。
            #
            # 【前情提要】：
            # {previous_summary}
            #
            # 要求：
            # 1. 内容充实，字数约 800 字。
            # 2. 必须承接【前情提要】的逻辑，不要重复。
            # """
            system_prompt = (
                f"你是一名专业作家，正在撰写关于《{self.topic}》的长文。\n"
                f"这是全文大纲（用于把控整体进度）：\n{outline_str}\n"
            )

            user_prompt = f"""
                        当前任务：撰写章节 "{title}"。
                        写作指导：{instruction}

                        === 上文回顾 (Context) ===
                        ...{previous_summary}
                        === 回顾结束 ===

                        要求：
                        1. 接着【上文回顾】的语气继续写，保持逻辑连贯。
                        2. 内容要详实，字数控制在 800 字左右。
                        3. 直接输出正文内容，不要输出标题。
                        """
            
            # try:
            #     response = client.chat.completions.create(
            #         model=MODEL_NAME,  # 使用配置的模型名
            #         messages=[{"role": "user", "content": prompt}],
            #         temperature=0.7
            #     )
            try:
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7
                )
                content = response.choices[0].message.content
                # self.articles.append(f"## {chapter}\n\n{content}")
                self.articles.append(f"## {title}\n\n{content}")
                
                # TODO: 更新 Context (核心考察点)
                # 简单策略：截取最后 200 字
                # 为了不爆 Token，只保留本段的最后 N 个字符作为下一段的引子
                # -----------------------------------------------------------
                # 截取最后 500 个字符。
                # 这里的逻辑是：不需要知道 5000 字之前写了啥，只需要知道最后一段话是什么，
                # 就能接得上语气。

                if len(content) > 500:
                    previous_summary = content[-500:]
                else:
                    previous_summary = content
                # 简单的防频控
                time.sleep(1)
                # previous_summary = content[-200:]
                
            # except Exception as e:
            #     print(f"⚠️ 章节 {chapter} 生成失败: {e}")
            except Exception as e:
                print(f"⚠️ 章节 {title} 生成失败: {e}")

    def save_result(self):
        if not self.articles:
            print("⚠️ 没有生成任何内容")
            return
            
        filename = "final_article.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# {self.topic}\n\n")
            f.write("\n\n".join(self.articles))
        print(f"\n🎉 文章已保存至 {filename}")

if __name__ == "__main__":
    print(f"🔌 Endpoint: {BASE_URL}")
    print(f"🧠 Model: {MODEL_NAME}\n")
    
    agent = LongArticleAgent("2025年 DeepSeek 对 AI 行业的影响")
    agent.step1_generate_outline()
    agent.step2_generate_content_loop()
    agent.save_result()