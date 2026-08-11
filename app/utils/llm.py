from dotenv import load_dotenv
import os
from functools import lru_cache
from langchain_openai import ChatOpenAI

load_dotenv()

@lru_cache(maxsize=20)
def get_llm(
    model: str = "gpt-4o-mini",
    temperature: float = 0,
    top_p: float = 1,
    seed: int = 42,
    n: int = 1,
) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=temperature,
        top_p=top_p,
        seed=seed,
        n=n,
    )


