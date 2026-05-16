import { useState, useEffect } from 'react';
import { LucideProvider } from 'lucide-react';
import Header from './components/Header';
import SearchBox from './components/SearchBox';
import MainLayout from './layouts/MainLayout';
import Report from './pages/Report';
import NewsAnalysis from './pages/NewsAnalysis';
import Disclosure from './pages/Disclosure';
import HomePage from './pages/Home';
import { BeatLoader } from 'react-spinners';
import { gfn_transaction } from './util/common-util';
import './index.css';
import './App.css';
import { MOCK } from './mock_data';

const PAGE_MAP = {
  report:      <Report />,
  news:        <NewsAnalysis />,
  disclosure:  <Disclosure />,
};

function App() {
  // 화면 제어
  const [activeTab, setActiveTab]           = useState('report'); // 탬 초기 선택 Report
  const [loading, setLoading]               = useState(false);
  const [searchCollapsed, setSearchCollapsed] = useState(false);  // 검색창 접힘 여부

  // 조회 조건
  const [allCompanies, setAllCompanies]     = useState([]);
  const [filteredData, setFilteredData]     = useState([]);
  const [searchResult, setSearchResult]     = useState(null);
  const [keyword, setKeyword]               = useState('');     // 조회 조건의 keyword
  const [selectedCorpCode, setSelectedCorpCode] = useState(null);
  const [companyName, setCompanyName]       = useState(null);   // 조회된 회사명
  const [stockCode, setStockCode]           = useState(null);

  // 조회 후 리턴 데이터
  const [reportData, setReportData]         = useState(null);
  const [evidenceNews, setEvidenceNews]     = useState([]);
  const [newsLoading, setNewsLoading]       = useState(false);
  const [combinedData, setCombinedData]     = useState(null);

  useEffect(() => {
    const fetchInitialData = async () => {
      const options = {
        svcId:  'initData',
        strUrl: '/api/initData',
        method: 'POST',
        pCall:  (svcId, responseData, errCd) => {
          if (errCd === 0) setAllCompanies(responseData.data);
        },
      };
      await gfn_transaction(options);
    };
    fetchInitialData();
  }, []);

// const code = responseData.data.reportData?.company_info?.stock_code ?? null;
// if (code && !responseData.data.newsData.evidence_news?.length) {
//     fetchNewsAnalysis(code);
// }

  const fetchNewsAnalysis = async (code) => {
    setNewsLoading(true);
    const options = {
      svcId:  'aiReport',
      strUrl: `/api/v1/report/comprehensive/${code}/ai`,
      method: 'GET',
      pCall:  (svcId, responseData, errCd) => {
        if (errCd === 0) {
          setEvidenceNews(responseData.data.newsData.evidence_news ?? []);
        }
        setNewsLoading(false);
      },
    };
    try {
      await gfn_transaction(options);
    } catch {
      setNewsLoading(false);
    }
  };

  const handleCompanySelect = (company) => {
    setKeyword(company.CORP_NAME);
    setSelectedCorpCode(company.CORP_CODE);
  };

  const handleKeywordChange = (value) => {
    setKeyword(value);
    setSelectedCorpCode(null);
  };

  const handleSearch = async (kw) => {
    const param = selectedCorpCode
      ? { corp_code: selectedCorpCode }
      : { keyword: kw };

    if (!selectedCorpCode && !kw) { alert('검색어를 입력해주세요.'); return; }

    // 내용 초기화
    setSearchResult(null);
    setCompanyName(null);
    setStockCode(null);
    setEvidenceNews([]);
    setNewsLoading(false);
    // 로딩바
    setLoading(true);

    // 전송 파라미터
    const options = {
      svcId:  'searchCompany',
      strUrl: '/api/searchCompany',
      param,
      method: 'POST',
      pCall:  (svcId, responseData, errCd, msgTp, msgCd, msgText) => {

        if(responseData.status === 'fail') {
          alert(responseData.message);
          setLoading(false);
          return;
        }
        // 데이터 체크
        const { reportData, newsData, disclosureData } = responseData?.data ?? {};

        if (!reportData || !newsData || !disclosureData) {
            alert('일부 데이터가 누락되었습니다.');
            
        } else {
            // 데이터 병합
            const combinedData = {
              ...reportData,
              ...disclosureData
            }

            console.log(combinedData)
            console.log(responseData.data.reportData)
            console.log(responseData.data.disclosureData)
            console.log("responseData.data.reportData")
            console.log(responseData.data.reportData)
            // useState 업데이트
            setSearchResult(responseData.data);
            setCompanyName(responseData.data.reportData?.company_name ?? keyword);
            const code = responseData.data.reportData?.company_info?.stock_code ?? null;
            setStockCode(code);
            setCombinedData(combinedData);
            setReportData(responseData.data.reportData);
            if (code) fetchNewsAnalysis(code);
        }

        setLoading(false);
      },
    };

    try {
      // 조회
      await gfn_transaction(options);
    } catch {
      setLoading(false);
    }
  };

  const renderPage = () => {
    if (!searchResult) return <HomePage />;

    const reportData     = searchResult.reportData;
    const newsData       = searchResult.newsData;
    const disclosureData = searchResult.disclosureData ?? MOCK;

    switch (activeTab) {
      case 'report':     return <Report reportData={combinedData} />;
      case 'news': {
        const mergedNewsData = { ...newsData, evidence_news: evidenceNews };
        return <NewsAnalysis newsData={mergedNewsData} newsLoading={newsLoading} />;
      }
      case 'disclosure': return <Disclosure reportData={combinedData} />;
    }
  };

  const handleRefresh = () => {
    setSearchResult(null);
    setCompanyName(null);
    setStockCode(null);
    setReportData(null);
    setEvidenceNews([]);
    setNewsLoading(false);
    setFilteredData([]);
    setActiveTab('report');
    setSearchCollapsed(false);
    setKeyword('');
  };

  const handleKeyIn = (keyword) => {
    if (!keyword) { setFilteredData([]); return; }
    setFilteredData(
      allCompanies.filter(
        (c) => c.CORP_NAME.includes(keyword) || c.CORP_CODE?.includes(keyword)
      )
    );
  };

  return (
    <LucideProvider>
      <Header onToggleSearch={() => setSearchCollapsed(v => !v)} searchCollapsed={searchCollapsed} onRefresh={handleRefresh} />
      <div className={`app-search-bar${searchCollapsed ? ' collapsed' : ''}`}>
        <SearchBox
          onSearch={handleSearch}
          onKeyIn={handleKeyIn}
          searchResults={filteredData}
          keyword={keyword}
          onKeywordChange={handleKeywordChange}
          onCompanySelect={handleCompanySelect}
        />
      </div>
      {loading && (
        <div className="app-loader">
          <BeatLoader color="#c084fc" size={10} />
        </div>
      )}
      <MainLayout activeTab={activeTab} onTabChange={setActiveTab} companyName={companyName} stockCode={stockCode}>
        {renderPage()}
      </MainLayout>
    </LucideProvider>
  );
}

export default App;