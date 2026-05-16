import React, { useState, useEffect } from 'react';

export function SearchBox({ onSearch, onKeyIn, searchResults, keyword, onKeywordChange }) {
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
    onKeywordChange(company.CORP_NAME);
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
  }

  return (
    <div style={{ position: 'relative', width: '100%', marginBottom: '20px' }}>
      <div style={{ display: 'flex', gap: '10px' }}>
        <input 
          type="text" 
          value={keyword}
          placeholder="기업명을 입력하세요"
          onChange={handleInputChange}
          onKeyDown={handleInputKeydown}
          style={{ flex: 1, padding: '10px', borderRadius: '4px', border: '1px solid #ccc' }}
          maxLength="20"
        />
        {/* 검색 결과가 있을 때만 ul 표시 */}
        {searchResults && searchResults.length > 0 && (
          <ul style={{ 
            position: 'absolute', // 아래 컨텐츠를 밀어내지 않음
            top: '45px', 
            left: 0, 
            right: 0, 
            backgroundColor: 'white', 
            border: '1px solid #ddd', 
            borderRadius: '4px',
            zIndex: 100, // 최상단에 위치
            maxHeight: '200px',
            overflowY: 'auto',
            listStyle: 'none',
            padding: 0,
            margin: 0,
            boxShadow: '0 4px 6px rgba(0,0,0,0.1)'
          }}>
          {searchResults.map((company, index) => (
              <li 
                key={index} 
                onClick={() => handleItemClick(company)}
                style={{ 
                  padding: '10px', 
                  cursor: 'pointer', 
                  borderBottom: '1px solid #eee',
                  // 포커스된 아이템 배경색 변경
                  backgroundColor: focusedIndex === index ? '#f0f0f0' : 'transparent'
                }}
                onMouseOver={() => setFocusedIndex(index)}
              >
                <strong>{company.CORP_NAME}</strong> <small style={{ color: '#888' }}>{company.CORP_CODE}</small>
              </li>
            ))}
          </ul>
      )}
        <button onClick={() => onSearch(keyword)} style={{ padding: '10px 20px' }}>분석</button>
      </div>

      
    </div>
    
  );
}

export default SearchBox;