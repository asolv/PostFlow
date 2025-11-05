from pytrends.request import TrendReq
import threading

# 하나의 TrendReq 세션을 재사용
_pytrends_lock = threading.Lock()
pytrends = TrendReq(hl="ko-KR", tz=540)

def get_pytrends():
    return pytrends, _pytrends_lock
