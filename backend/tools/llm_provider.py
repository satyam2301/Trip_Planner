import os
from dotenv import load_dotenv

load_dotenv()

def get_llm(max_tokens: int = 4000, temperature: float = 0.2):
    """
    Returns the configured LLM client.
    Always prioritizes Codecrafter (gpt-5.6-luna via https://codecraftapi.com/v1)
    as configured in codecraftertesting.py.
    """
    codecrafter_key = os.getenv("CODECRAFTER_API_KEY")
    if codecrafter_key and codecrafter_key.strip():
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url="https://codecraftapi.com/v1",
            api_key=codecrafter_key.strip(),
            model="gpt-5.6-luna",
            max_tokens=max_tokens,
            temperature=temperature
        )

    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key and groq_key.strip():
        from langchain_groq import ChatGroq
        return ChatGroq(
            model="qwen/qwen3.8-27b",
            max_tokens=min(max_tokens, 2000),
            temperature=temperature
        )

    hf_token = os.getenv("HF_TOKEN")
    if hf_token and hf_token.strip():
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=hf_token.strip(),
            model="meta-llama/Llama-3.3-70B-Instruct",
            max_tokens=max_tokens,
            temperature=temperature
        )

    raise ValueError("No valid LLM API key found (CODECRAFTER_API_KEY, GROQ_API_KEY, or HF_TOKEN).")


def get_fast_llm(max_tokens: int = 1500, temperature: float = 0.1):
    """Alias to get_llm to ensure Codecrafter is consistently used."""
    return get_llm(max_tokens=max_tokens, temperature=temperature)
