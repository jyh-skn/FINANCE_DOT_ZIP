"""
news_vector_ingest_service.py

Tavily 검색 결과(searched_news)를 Vector DB(Pinecone)에 실시간 적재하는 모듈입니다.

역할:
1. news_search_service.py가 반환한 searched_news를 표준 뉴스 문서 형식으로 정규화합니다.
2. 뉴스 title/content/url/published_date를 하나의 text로 구성합니다.
3. 긴 뉴스 본문을 chunk로 나눕니다.
4. OpenAI text-embedding-3-small로 embedding합니다.
5. Pinecone index=finance-dot-news, namespace=stock_code에 upsert합니다.
6. metadata는 기존 Vector DB schema에 맞춰 data_type="news"로 저장합니다.

전제:
- .env에 PINECONE_API_KEY가 있어야 합니다.
- .env에 PINECONE_INDEX_NAME이 있으면 사용하고, 없으면 finance-dot-news를 기본값으로 사용합니다.
- .env에 OPENAI_API_KEY가 있어야 합니다.
- Pinecone index는 이미 생성되어 있다고 가정합니다.
  검색/리포트 생성 중 새 index를 만들지 않습니다.
"""

import hashlib
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_INDEX_NAME = "finance-dot-news"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


# ---------------------------------------------------------------------
# 1. 공통 유틸
# ---------------------------------------------------------------------

def safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def normalize_year(value: Any, fallback: Optional[int] = None) -> Optional[int]:
    if value is None or value == "":
        return fallback

    try:
        return int(float(value))
    except Exception:
        return fallback


def normalize_date(value: Any, fallback_year: Optional[int] = None) -> str:
    """
    published_date/date 값을 YYYY-MM-DD 형태에 가깝게 정리합니다.
    정확한 날짜가 없고 fallback_year가 있으면 YYYY-01-01을 반환합니다.
    """

    text = safe_text(value).strip()

    if not text:
        if fallback_year:
            return f"{fallback_year}-01-01"
        return ""

    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]

    normalized = text.replace(".", "-").replace("/", "-")

    if len(normalized) >= 10 and normalized[4:5] == "-" and normalized[7:8] == "-":
        return normalized[:10]

    return text


def build_hash_id(value: str) -> str:
    value = safe_text(value).strip()

    if not value:
        value = datetime.now().isoformat()

    return hashlib.md5(value.encode("utf-8")).hexdigest()


def split_text(
    text: str,
    chunk_size: int = 1200,
    chunk_overlap: int = 150,
) -> List[str]:
    """
    간단한 문자 단위 chunking 함수입니다.
    """

    text = safe_text(text).strip()

    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(0, end - chunk_overlap)

    return chunks


# ---------------------------------------------------------------------
# 2. ai_input / 뉴스 정규화
# ---------------------------------------------------------------------

def get_company_info(ai_input: Dict[str, Any]) -> Dict[str, Any]:
    return ai_input.get("company_info", {}) or {}


def get_industry_info(ai_input: Dict[str, Any]) -> Dict[str, Any]:
    return ai_input.get("industry_info", {}) or {}


def get_company_name(ai_input: Dict[str, Any]) -> str:
    company_info = get_company_info(ai_input)
    return company_info.get("company_name") or ai_input.get("company_name") or ""


def get_stock_code(ai_input: Dict[str, Any]) -> str:
    company_info = get_company_info(ai_input)
    return company_info.get("stock_code") or ai_input.get("stock_code") or ""


def get_industry_group(ai_input: Dict[str, Any]) -> str:
    industry_info = get_industry_info(ai_input)
    return industry_info.get("industry_group", "")


def get_analysis_year(ai_input: Dict[str, Any]) -> Optional[int]:
    return normalize_year(ai_input.get("analysis_year"))


def get_default_signal_info(ai_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    searched_news 개별 item에 signal 정보가 없을 때 fallback으로 사용할 signal 정보를 가져옵니다.
    """

    detected_changes = ai_input.get("detected_changes", []) or []

    if not detected_changes:
        return {
            "signal_type": "neutral",
            "signal_code": "GENERAL_TREND",
            "metric_key": "general_company_trend",
            "metric_label": "기업 일반 동향",
        }

    first_change = detected_changes[0] or {}

    return {
        "signal_type": first_change.get("signal_type") or "unknown",
        "signal_code": first_change.get("signal_code") or "unknown",
        "metric_key": first_change.get("metric_key"),
        "metric_label": first_change.get("metric_label"),
    }


def build_news_document_text(news_item: Dict[str, Any]) -> str:
    """
    뉴스 title/content/url/date를 embedding 대상 text로 구성합니다.
    """

    title = safe_text(news_item.get("title")).strip()
    content = (
        safe_text(news_item.get("content")).strip()
        or safe_text(news_item.get("raw_content")).strip()
        or safe_text(news_item.get("snippet")).strip()
        or safe_text(news_item.get("summary")).strip()
    )
    url = safe_text(news_item.get("url")).strip() or safe_text(news_item.get("source_url")).strip()
    published_date = safe_text(news_item.get("published_date")).strip() or safe_text(news_item.get("date")).strip()

    parts = []

    if title:
        parts.append(f"[뉴스 제목]\n{title}")

    if published_date:
        parts.append(f"[발행일]\n{published_date}")

    if content:
        parts.append(f"[뉴스 내용]\n{content}")

    if url:
        parts.append(f"[URL]\n{url}")

    return "\n\n".join(parts).strip()


def normalize_news_item(
    news_item: Dict[str, Any],
    ai_input: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Tavily searched_news item을 Vector DB 저장용 표준 구조로 정규화합니다.
    """

    company_name = get_company_name(ai_input)
    stock_code = get_stock_code(ai_input)
    industry_group = get_industry_group(ai_input)
    analysis_year = get_analysis_year(ai_input)
    default_signal = get_default_signal_info(ai_input)

    title = safe_text(news_item.get("title")).strip() or "뉴스"
    url = safe_text(news_item.get("url")).strip() or safe_text(news_item.get("source_url")).strip()
    published_date = safe_text(news_item.get("published_date")).strip() or safe_text(news_item.get("date")).strip()
    year = normalize_year(news_item.get("year"), fallback=analysis_year)
    date = normalize_date(published_date, fallback_year=year)

    content = (
        safe_text(news_item.get("content")).strip()
        or safe_text(news_item.get("raw_content")).strip()
        or safe_text(news_item.get("snippet")).strip()
        or safe_text(news_item.get("summary")).strip()
    )

    signal_type = news_item.get("signal_type") or default_signal.get("signal_type") or "unknown"
    signal_code = news_item.get("signal_code") or default_signal.get("signal_code") or "unknown"
    metric_key = news_item.get("metric_key") or default_signal.get("metric_key")
    metric_label = news_item.get("metric_label") or default_signal.get("metric_label")

    text = build_news_document_text(
        {
            **news_item,
            "title": title,
            "content": content,
            "url": url,
            "published_date": date or published_date,
        }
    )

    return {
        "title": title,
        "url": url,
        "source_url": url,
        "published_date": date or published_date,
        "date": date,
        "year": year,
        "content": content,
        "text": text,
        "company_name": company_name,
        "stock_code": stock_code,
        "industry_group": industry_group,
        "signal_type": signal_type,
        "signal_code": signal_code,
        "metric_key": metric_key,
        "metric_label": metric_label,
    }


def build_news_vectors_payload(
    searched_news: List[Dict[str, Any]],
    ai_input: Dict[str, Any],
    chunk_size: int = 1200,
    chunk_overlap: int = 150,
) -> Tuple[List[str], List[Dict[str, Any]], List[str]]:
    """
    Pinecone upsert에 사용할 texts, metadatas, ids를 생성합니다.
    """

    texts = []
    metadatas = []
    ids = []

    for news_item in searched_news:
        normalized = normalize_news_item(news_item=news_item, ai_input=ai_input)
        text = normalized.get("text", "")

        if not text:
            continue

        chunks = split_text(text=text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        source_key = normalized.get("source_url") or normalized.get("title") or text[:100]
        base_id = build_hash_id(source_key)

        for chunk_index, chunk in enumerate(chunks):
            chunk_id = f"{base_id}_{chunk_index}"

            metadata = {
                "text": chunk,
                "data_type": "news",
                "company_name": normalized.get("company_name"),
                "stock_code": normalized.get("stock_code"),
                "stock_codes": [normalized.get("stock_code")] if normalized.get("stock_code") else [],
                "year": normalized.get("year"),
                "date": normalized.get("date") or normalized.get("published_date") or "",
                "published_date": normalized.get("published_date") or "",
                "signal_type": normalized.get("signal_type"),
                "signal_code": normalized.get("signal_code"),
                "industry_group": normalized.get("industry_group"),
                "source": normalized.get("title"),
                "source_url": normalized.get("source_url"),
                "title": normalized.get("title"),
                "metric_key": normalized.get("metric_key"),
                "metric_label": normalized.get("metric_label"),
                "chunk_index": chunk_index,
            }

            texts.append(chunk)
            metadatas.append(metadata)
            ids.append(chunk_id)

    return texts, metadatas, ids


# ---------------------------------------------------------------------
# 3. Pinecone Upsert
# ---------------------------------------------------------------------

def get_pinecone_index_name(index_name: Optional[str] = None) -> str:
    return index_name or os.getenv("PINECONE_INDEX_NAME") or DEFAULT_INDEX_NAME


def get_embeddings_model(model_name: str = DEFAULT_EMBEDDING_MODEL):
    try:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=model_name)

    except Exception as error:
        raise RuntimeError(
            "OpenAIEmbeddings 생성에 실패했습니다. langchain_openai 설치와 OPENAI_API_KEY 설정을 확인하세요."
        ) from error


def embed_texts(texts: List[str], model_name: str = DEFAULT_EMBEDDING_MODEL) -> List[List[float]]:
    embeddings = get_embeddings_model(model_name=model_name)
    return embeddings.embed_documents(texts)


def upsert_vectors_to_pinecone(
    texts: List[str],
    metadatas: List[Dict[str, Any]],
    ids: List[str],
    namespace: str,
    index_name: Optional[str] = None,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 50,
) -> Dict[str, Any]:
    """
    texts/metadatas/ids를 Pinecone에 upsert합니다.
    index는 새로 생성하지 않고 기존 index에만 연결합니다.
    """

    if not texts:
        return {
            "upserted_count": 0,
            "namespace": namespace,
            "index_name": get_pinecone_index_name(index_name),
            "reason": "No texts to upsert.",
        }

    try:
        from pinecone import Pinecone
    except Exception as error:
        raise RuntimeError("pinecone 패키지를 불러오지 못했습니다. 설치 여부를 확인하세요.") from error

    api_key = os.getenv("PINECONE_API_KEY")

    if not api_key:
        raise RuntimeError("PINECONE_API_KEY가 설정되어 있지 않습니다.")

    index_name = get_pinecone_index_name(index_name)
    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)

    total_upserted = 0

    for start in range(0, len(texts), batch_size):
        end = start + batch_size
        batch_texts = texts[start:end]
        batch_metadatas = metadatas[start:end]
        batch_ids = ids[start:end]

        vectors = embed_texts(texts=batch_texts, model_name=embedding_model)

        payload = []
        for vector_id, vector, metadata in zip(batch_ids, vectors, batch_metadatas):
            payload.append({"id": vector_id, "values": vector, "metadata": metadata})

        index.upsert(vectors=payload, namespace=namespace)
        total_upserted += len(payload)

    return {
        "upserted_count": total_upserted,
        "namespace": namespace,
        "index_name": index_name,
        "embedding_model": embedding_model,
    }


def upsert_searched_news_to_vector_db(
    searched_news: List[Dict[str, Any]],
    ai_input: Dict[str, Any],
    index_name: Optional[str] = None,
    namespace: Optional[str] = None,
    chunk_size: int = 1200,
    chunk_overlap: int = 150,
) -> Dict[str, Any]:
    """
    searched_news를 Vector DB에 적재합니다.

    현재 팀 Vector DB는 기본 namespace("")에 데이터를 저장하고,
    stock_code는 metadata filter로 검색하는 구조에 맞춥니다.
    """

    stock_code = get_stock_code(ai_input)

    if not stock_code:
        raise ValueError("metadata에 저장할 stock_code가 없습니다.")

    # 중요:
    # 기존 retriever가 기본 namespace("") + metadata stock_code filter로 검색하는 구조이므로
    # news도 동일하게 기본 namespace에 적재합니다.
    namespace = "" if namespace is None else namespace

    texts, metadatas, ids = build_news_vectors_payload(
        searched_news=searched_news,
        ai_input=ai_input,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    result = upsert_vectors_to_pinecone(
        texts=texts,
        metadatas=metadatas,
        ids=ids,
        namespace=namespace,
        index_name=index_name,
    )

    return {
        "source": "news_vector_ingest_service",
        "searched_news_count": len(searched_news),
        "chunk_count": len(texts),
        "upserted_count": result.get("upserted_count", 0),
        "namespace": result.get("namespace"),
        "index_name": result.get("index_name"),
        "embedding_model": result.get("embedding_model"),
    }


if __name__ == "__main__":
    print(
        "news_vector_ingest_service.py는 Tavily searched_news를 Vector DB에 적재하는 모듈입니다.\n"
        "실제 실행은 comprehensive_report_service.py에서 searched_news 생성 후 호출하세요."
    )
