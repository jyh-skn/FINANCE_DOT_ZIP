import React, { useState, useEffect } from 'react';

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
  }

  return (
    <div style={{ display: 'flex', gap: '10px', width: '100%' }}>
  
      {/* 1. Input과 드롭다운을 감싸는 컨테이너 (여기에 position: relative를 줍니다) */}
      <div style={{ position: 'relative', flex: 1 }}>
        <input 
          type="text" 
          value={keyword}
          placeholder="기업명을 입력하세요"
          onChange={handleInputChange}
          onKeyDown={handleInputKeydown}
          style={{ 
            width: '100%',
            height: '100%',
            padding: '10px', 
            borderRadius: '4px', 
            border: '1px solid #ccc',
            boxSizing: 'border-box'
          }}
          maxLength="20"
        />
        {/* 검색 결과가 있을 때만 ul 표시 */}
        {searchResults && searchResults.length > 0 && (
          <ul style={{ 
            position: 'absolute', // 아래 컨텐츠를 밀어내지 않음
            top: '45px', 
            left: 0, 
            
            width: '100%',
            backgroundColor: '#1e2330', 
            border: '1px solid #343d52',
            borderRadius: '4px',
            zIndex: 100,
            maxHeight: '200px',
            overflowY: 'auto',
            listStyle: 'none',
            padding: 0,
            margin: 0,
            boxShadow: '0 8px 16px rgba(0, 0, 0, 0.4)'
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
                  backgroundColor: focusedIndex === index ? '#f0f0f0' : 'transparent',
                  textAlign: 'left',
                  fontSize: '12px',
                  height: '20px',
                  color: '#8899bb',
                }}
                onMouseOver={() => setFocusedIndex(index)}
              >
                {company.CORP_NAME} <small style={{ color: '#888' }}>{company.CORP_CODE}</small>
              </li>
            ))}
          </ul>
        )}
      </div>
        <button onClick={() => onSearch(keyword)} style={{ padding: '10px 20px' }}>분석</button>
    </div>
    
  );
}

export default SearchBox;