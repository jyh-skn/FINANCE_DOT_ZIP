export default function HomePage() {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '60vh',
      gap: '12px',
      color: 'var(--text)',
    }}>
      <p style={{ fontSize: '15px', color: 'var(--text-h)' }}>
        기업명으로 종목코드를 검색하세요.
      </p>
      <p style={{ fontSize: '13px' }}>
        예: 삼성전자, SK하이닉스, 현대자동차, LG화학, 카카오
      </p>
    </div>
  );
}
