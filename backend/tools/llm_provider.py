import os
from dotenv import load_dotenv

load_dotenv()

def _get_key(key_name: str) -> str:
    """Retrieve key from os.environ or streamlit secrets safely."""
    val = os.getenv(key_name)
    if val and val.strip():
        return val.strip()
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key_name in st.secrets:
            s_val = str(st.secrets[key_name]).strip()
            if s_val:
                return s_val
    except Exception:
        pass
    return ""


def get_llm(max_tokens: int = 4000, temperature: float = 0.2):
    """
    Returns the configured LLM client.

    """
    # 1. Codecrafter API
    codecrafter_key = _get_key("CODECRAFTER_API_KEY")
    if codecrafter_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url="https://codecraftapi.com/v1",
            api_key=codecrafter_key,
            model="gpt-5.6-luna",
            max_tokens=max_tokens,
            temperature=temperature
        )

    # 2. Groq API
    groq_key = _get_key("GROQ_API_KEY")
    if groq_key:
        from langchain_groq import ChatGroq
        return ChatGroq(
            api_key=groq_key,
            model="llama-3.3-70b-versatile",
            max_tokens=min(max_tokens, 2000),
            temperature=temperature
        )

    # 3. Direct OpenAI API
    openai_key = _get_key("OPENAI_API_KEY")
    if openai_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            api_key=openai_key,
            model="gpt-4o-mini",
            max_tokens=max_tokens,
            temperature=temperature
        )

    # 4. HuggingFace Serverless Router
    hf_token = _get_key("HF_TOKEN")
    if hf_token:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=hf_token,
            model="meta-llama/Llama-3.3-70B-Instruct",
            max_tokens=max_tokens,
            temperature=temperature
        )

    raise ValueError("No valid LLM API key found in environment or secrets (CODECRAFTER_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, or HF_TOKEN).")


def get_fast_llm(max_tokens: int = 1500, temperature: float = 0.1):
    """Alias to get_llm to ensure Codecrafter is consistently used."""
    return get_llm(max_tokens=max_tokens, temperature=temperature)
