import React, { useState, useEffect } from 'react';
import './SearchBox.css';

export function SearchBox({ onSearch, onKeyIn, searchResults, keyword, onKeywordChange, onCompanySelect }) {
  // 현재 키보드로 포커스된 아이템의 인덱스 (-1은 선택 없음)
  const [focusedIndex, setFocusedIndex] = useState(-1);

  // 결과 리스트가 변하면 포커스 초기화
  useEffect(() => {
    setFocusedIndex(-1);
  }, [searchResults]);

  const handleInputChange = (e) => {
    const value = e.target.value;
    onKeywordChange(value);
    onKeyIn(value);
  };

  const handleItemClick = (company) => {
    onCompanySelect(company);
    onKeyIn("");
  };

  const handleInputKeydown = (e) => {

    if (!searchResults || searchResults.length === 0) {
      if (e.key === "Enter") onSearch(keyword);
      return;
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault(); // 스크롤 방지
        setFocusedIndex((prev) => (prev < searchResults.length - 1 ? prev + 1 : prev));
        break;
      case "ArrowUp":
        e.preventDefault();
        setFocusedIndex((prev) => (prev > 0 ? prev - 1 : -1));
        break;
      case "Enter":
        if (focusedIndex >= 0) {
          // 리스트에서 선택된 항목이 있을 때
          handleItemClick(searchResults[focusedIndex]);
        } else {
          // 선택된 항목이 없을 때 일반 검색
          onSearch(keyword);
          onKeyIn("");
        }
        break;
      case "Escape":
        onKeyIn(""); // 리스트 닫기
        break;
      default:
        break;
    }
  };

  return (
    <div className="sb-wrap">
      <div className="sb-input-wrap">
        <input
          className="sb-input"
          type="text"
          value={keyword}
          placeholder="기업명을 입력하세요"
          onChange={handleInputChange}
          onKeyDown={handleInputKeydown}
          maxLength="20"
        />
        {/* 검색 결과가 있을 때만 ul 표시 */}
        {searchResults && searchResults.length > 0 && (
          <ul className="sb-dropdown">
            {searchResults.map((company, index) => (
              <li
                key={index}
                className={`sb-item${focusedIndex === index ? ' focused' : ''}`}
                onClick={() => handleItemClick(company)}
                onMouseOver={() => setFocusedIndex(index)}
              >
                {company.CORP_NAME}
                <small className="sb-item-code">{company.CORP_CODE}</small>              </li>
            ))}
          </ul>
        )}
      </div>
      <button className="sb-search-btn" onClick={() => onSearch(keyword)}>분석</button>
	</div>
    
  );
}

export default SearchBox;