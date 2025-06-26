from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

def main():

    llm = ChatOpenAI(model="gpt-3.5-turbo")

    messages = [
        SystemMessage(content="You are a helpful assistant!"),
        HumanMessage(content="What is the capital of France?"),
    ]

    result = llm.invoke(messages).content
    print("LLM output:\n", result)

if __name__ == "__main__":
    main()
