"""
Simple terminal chat loop to test the real agent end-to-end with your actual
OpenRouter API key. Type messages, see which tools get called along the way,
and read the final answer (with disclaimer). Type 'quit' or 'exit' to stop.

Run with:
    cd app
    python scripts/chat_test.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from agent.graph import build_graph


def run():
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY environment variable is not set.")
        print('Set it with: $env:OPENROUTER_API_KEY="your-key-here"')
        sys.exit(1)

    print("Building agent graph (loading the embedding model on first message - may take a moment)...")
    app = build_graph()
    config = {"configurable": {"thread_id": "chat-test-session"}}

    print("\nPharmacy assistant ready. Type your message (English or Arabic), or 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if user_input.lower() in ("quit", "exit"):
            print("Goodbye.")
            break
        if not user_input:
            continue

        try:
            previous_message_count = len(app.get_state(config).values.get("messages", []))
        except Exception:
            previous_message_count = 0

        try:
            result = app.invoke(
                {"messages": [HumanMessage(content=user_input)], "lang": ""},
                config=config,
            )
        except Exception as e:
            print(f"  ERROR: {e}\n")
            continue

        # Only show tool activity from THIS turn, not the whole accumulated history
        new_messages = result["messages"][previous_message_count:]
        for msg in new_messages:
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    print(f"  [tool call] {tc['name']}({tc['args']})")
            elif isinstance(msg, ToolMessage):
                preview = msg.content[:150] + ("..." if len(msg.content) > 150 else "")
                print(f"  [tool result] {preview}")

        final_answer = result["messages"][-1].content
        print(f"\nAssistant: {final_answer}\n")


if __name__ == "__main__":
    run()