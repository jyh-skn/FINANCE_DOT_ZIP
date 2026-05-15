from src.vector_db.retriever import search_similar_documents


def main():
    results = search_similar_documents(
        query="삼성전자 2023 영업이익 감소 반도체 업황",
        stock_code="005930",
        data_type="news",
        top_k=5,
        with_score=True,
    )

    print("[News Vector Direct Search Test]")
    print("count:", len(results))

    for idx, item in enumerate(results, start=1):
        print(f"\n[Result {idx}]")
        print("score:", item.get("score"))
        print("metadata:", item.get("metadata"))
        print("content:", item.get("content", "")[:500])


if __name__ == "__main__":
    main()