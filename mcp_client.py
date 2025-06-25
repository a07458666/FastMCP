import asyncio
import json
from fastmcp import Client
from fastmcp.client.logging import LogMessage
import google.generativeai as genai
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
from google import genai
import re


llm_client = genai.Client(api_key="AIzaSyBMCabBfvTIfiHVYYcpbJjrqfDwnEFV82s")

async def log_handler(message: LogMessage):
    print(f"Server log: {message.data}")

async def progress_handler(progress: float, total: float | None, message: str | None):
    print(f"Progress: {progress}/{total} - {message}")

async def sampling_handler(messages, params, context):
    user_message = messages[-1]["content"]

    prompt = f"""
    You are an intelligent assistant. Based on the user's input and the available tools, resources, and prompts listed below,
    decide the most appropriate MCP tool to invoke, and—if beneficial—include an optional follow-up prompt request
    for further explanation or summarization.

    📌 Note:
    - If the tool requires system data, refer to the corresponding resource URI like "minio://case_001/all_query_data". DO NOT include the actual data.
    - If a prompt should be used to explain or summarize the tool result, include a "post_prompt" field.

    Available tools:
    {await client.list_tools()}

    Available resources:
    {await client.list_resources()}

    Available prompts:
    {await client.list_prompts()}

    📝 Output format (JSON):
    {{
    "tool": "tool_name",
    "input": {{
        "param1": value,
        ...
    }},
    "post_prompt": {{
        "prompt": "prompt_name",
        "input": {{
        "param1": value,
        ...
        }}
    }} (optional)
    }}

    Now, convert the following user request into a valid MCP tool invocation:

    "{user_message}"
    """
    
    print(f"🔍 LLM 請求內容 {prompt}")

    response = llm_client.models.generate_content(model="gemini-2.0-flash", contents=prompt)

    try:
        raw_text = response.text
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.IGNORECASE)
        tool_call = json.loads(cleaned)
        print("✅ LLM 輸出 JSON：", tool_call)
        return tool_call
    except Exception as e:
        print("❌ LLM 輸出不是合法 JSON：", response.text)
        return {
            "tool": "echo",
            "input": {"message": f"無法理解：{user_message}"}
        }

client = Client(
    "http://127.0.0.1:9000/sse",
    log_handler=log_handler,
    progress_handler=progress_handler,
    sampling_handler=sampling_handler,
    timeout=30.0
)


async def main():
    async with client:
        await client.ping()
        print("✅ 已連線 MCP Server。輸入 exit 離開。\n")

        tools = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()

        print("🛠️ 可用工具：", [tool.name for tool in tools])
        print("📦 可用資源：", [res.name for res in resources])
        print("💡 可用提示：", [prompt.name for prompt in prompts])

        config = await client.read_resource("minio://case_001/all_query_data")

        print("✅ 配置數據：", config)
        messages = []

        while True:
            user_input = input("請輸入你的問題：")
            if user_input.strip().lower() in ["exit", "quit"]:
                break

            # 加入使用者訊息
            messages.append({"role": "user", "content": user_input})

            # 使用 Gemini 進行推論
            llm_decision = await sampling_handler(messages, {}, {})

            tool = llm_decision.get("tool")
            tool_input = llm_decision.get("input")

            if isinstance(tool_input, dict):
                for key, value in tool_input.items():
                    if isinstance(value, str) and value.startswith("minio://"):
                        print(f"📦 從 Resource {key} 讀取資料：{value}")
                        try:
                            resource_data = await client.read_resource(value)
                            data = resource_data[0].text
                            parsed_data = json.loads(data)
                            tool_input[key] = parsed_data
                        except Exception as e:
                            print(f"❌ Resource 讀取失敗：{e}")
                            continue
            try:
                print(f"🔧 正在調用工具：{tool}，輸入參數：{tool_input}")
                result = await client.call_tool(tool, tool_input)
                print("✅ 回應：", result)

                # 加入 Assistant 回應到對話歷史
                messages.append({"role": "assistant", "content": str(result)})

            except Exception as e:
                error_msg = f"❌ 發生錯誤：{e}"
                print(error_msg)
                messages.append({"role": "assistant", "content": error_msg})

            if "post_prompt" in llm_decision:
                pp = llm_decision["post_prompt"]
                prompt_text = await client.get_prompt(pp["prompt"], {"bad_wafer_id": result[0].text})
                print("📨 Prompt：", prompt_text)
                gemini_prompt = "\n".join(m.content.text for m in prompt_text.messages if m.content.text)

                explanation = llm_client.models.generate_content(
                    model="gemini-2.0-flash", contents=gemini_prompt,
                )
                print("🧠 LLM 解釋：", explanation.text)
                messages.append({"role": "assistant", "content": explanation.text})
asyncio.run(main())