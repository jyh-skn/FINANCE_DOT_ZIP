import os
from pathlib import Path

from dotenv import load_dotenv
from pinecone import Pinecone


def main():
    backend_dir = Path(__file__).resolve().parents[1]
    env_path = backend_dir / ".env"

    load_dotenv(env_path)

    api_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX_NAME", "finance-dot-news")

    print("[ENV CHECK]")
    print("env_path:", env_path)
    print("PINECONE_API_KEY exists:", bool(api_key))
    print("PINECONE_INDEX_NAME:", index_name)

    if not api_key:
        raise RuntimeError("PINECONE_API_KEY가 비어 있습니다. backend/.env 위치를 확인하세요.")

    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)

    stats = index.describe_index_stats()

    print("\n[Pinecone Index Stats]")
    print(stats)


if __name__ == "__main__":
    main()