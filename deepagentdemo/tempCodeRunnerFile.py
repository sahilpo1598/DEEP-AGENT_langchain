import gradio as gr
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek
from tavily import TavilyClient
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware import SummarizationMiddleware
from typing import Literal

# 1. Load API Keys
load_dotenv()

# 2. Setup the Web Search Tool
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Run a web search"""
    return tavily_client.search(
        query, max_results=max_results,
        include_raw_content=include_raw_content, topic=topic
    )

# 3. Setup the Model and Backend
model = ChatDeepSeek(model="deepseek-chat")
backend = FilesystemBackend(root_dir=".", virtual_mode=True)

# 4. THE FIX: Use absolute token counts instead of a fraction
summarization_middleware = SummarizationMiddleware(
    model=model, 
    trigger=("tokens", 60000),  # Trigger at 60,000 tokens (fixed number)
    keep=("tokens", 3000)
)

# 5. Load AGENTS.md
agents_md_path = Path("AGENTS.md")
if agents_md_path.exists():
    system_prompt = agents_md_path.read_text(encoding="utf-8")
else:
    system_prompt = "You are an elite AI Research Assistant. Save your work to files."

# 6. Create the Deep Agent
print("🧠 Building your Deep Agent...")
agent = create_deep_agent(
    model=model,
    system_prompt=system_prompt,
    tools=[internet_search],
    backend=backend,
    middleware=[summarization_middleware]
)
print("✅ Deep Agent is ready!")

# 7. The Gradio Chat Function
def chat_with_deep_agent(message, history):
    config = {"configurable": {"thread_id": "gradio_chat_session_1"}}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": message}]},
        config=config
    )
    return result["messages"][-1].content

# 8. Build and Launch the Interface
demo = gr.ChatInterface(
    fn=chat_with_deep_agent,
    title="Deep Agent Research Assistant",
    description="Ask me to research topics, write code, or save files to your disk!"
)

if __name__ == "__main__":
    demo.launch()