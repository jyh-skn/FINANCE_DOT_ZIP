import axios from 'axios';

/**
 * 공통 통신 함수 (Global Transaction)
 * @param {Object} options - 통신 옵션 객체
 */
export const gfn_transaction = async (options) => {
  const {
    svcId = '',           // 서비스 ID
    strUrl = '',          // 호출 URL
    param = {},           // 요청 파라미터 (POST의 body 또는 GET의 query)
    pCall = null,         // 콜백 함수
    method = 'POST',      // 기본 메소드는 POST (필요에 따라 변경 가능)
  } = options;

  try {
    // 1. API 호출 (axios 사용)
    const response = await axios({
      method: method,
      url: strUrl,
      // GET일 때는 params, 그 외(POST, PUT 등)에는 data에 실어서 보냄
      [method.toUpperCase() === 'GET' ? 'params' : 'data']: param,
    });

    console.log(response);

    // 2. 서버 응답 성공 (HTTP 200)
    if (pCall && typeof pCall === 'function') {
    
      const responseData = response.data;
      const errCd = responseData.status === "fail" ? -1 : 0; // 서버가 주는 에러 코드 (0이면 성공)
      const msgText = responseData.msgText ?? 'Success';

      // 콜백 실행: (svcId, responseData, errCd, msgTp, msgCd, msgText)
      pCall(svcId, responseData, errCd, null, null, msgText);
    }
  } catch (error) {
    // 3. 네트워크 에러나 서버 에러 (HTTP 400, 500 등)
    console.error(`[API Error - ${svcId}]`, error);
    
    if (pCall && typeof pCall === 'function') {
      const errorMsg = error.response?.data?.message || '네트워크 오류가 발생했습니다.';
      pCall(svcId, null, -1, 'E', 'ERROR', errorMsg);
    }
    
    // 에러를 위로 던져서 호출한 쪽(try-catch)에서도 알게 함
    throw error;
  }
};