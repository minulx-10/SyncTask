import aiohttp
import os

async def fetch_neis_timetable(date_str: str, grade: str, class_nm: str) -> list:
    if not os.getenv("NEIS_API_KEY"):
        return None

    url = "https://open.neis.go.kr/hub/hisTimetable"
    params = {
        "KEY": os.getenv("NEIS_API_KEY"), 
        "Type": "json", "pIndex": 1, "pSize": 50,
        "ATPT_OFCDC_SC_CODE": "F10", "SD_SCHUL_CODE": "7380292",  
        "ALL_TI_YMD": date_str, "GRADE": str(grade), "CLASS_NM": str(class_nm)
    }
    try:
        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=5)
            async with session.get(url, params=params, timeout=timeout) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                    except aiohttp.ContentTypeError:
                        return None
                    
                    if "hisTimetable" in data:
                        rows = data["hisTimetable"][1]["row"]
                        timetable_dict = {}
                        for r in rows:
                            perio = int(r["PERIO"])
                            if perio not in timetable_dict:
                                timetable_dict[perio] = r["ITRT_CNTNT"]
                        return sorted(timetable_dict.items())
                    return []
    except Exception:
        return None
    return None


async def fetch_neis_school_schedule(start_date: str, end_date: str) -> list:
    if not os.getenv("NEIS_API_KEY"):
        return None

    url = "https://open.neis.go.kr/hub/SchoolSchedule"
    params = {
        "KEY": os.getenv("NEIS_API_KEY"),
        "Type": "json", "pIndex": 1, "pSize": 100,
        "ATPT_OFCDC_SC_CODE": "F10", "SD_SCHUL_CODE": "7380292",  # 광주소프트웨어마이스터고
        "AA_FROM_YMD": start_date, "AA_TO_YMD": end_date
    }
    try:
        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=5)
            async with session.get(url, params=params, timeout=timeout) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                    except aiohttp.ContentTypeError:
                        return None
                    
                    if "SchoolSchedule" in data:
                        rows = data["SchoolSchedule"][1]["row"]
                        schedule = []
                        for r in rows:
                            # 매주 반복되는 '토요휴업일' 같은 불필요한 데이터 필터링
                            if r["EVENT_NM"] not in ["토요휴업일", "휴업일"]: 
                                schedule.append((r["AA_YMD"], r["EVENT_NM"]))
                        
                        # 연속으로 같은 행사명이 반복되는 경우 날짜 범위로 병합
                        # 예: 여름방학 7/20, 7/21, ..., 8/15 → 7/20~8/15 여름방학
                        if not schedule:
                            return []
                        merged = []
                        start, prev_name = schedule[0][0], schedule[0][1]
                        prev_date = start
                        for date, name in schedule[1:]:
                            if name == prev_name:
                                prev_date = date
                            else:
                                merged.append((start, prev_date if prev_date != start else None, prev_name))
                                start, prev_date, prev_name = date, date, name
                        merged.append((start, prev_date if prev_date != start else None, prev_name))
                        return merged
                    return []
    except Exception:
        return None
    return None


async def fetch_neis_exam_dates(year: int, month: int = None) -> dict:
    """
    현재 학기의 학사일정에서 중간(1차)/기말(2차) 시험 날짜를 자동 감지한다.
    학기 구분: 1학기(3~8월), 2학기(9~2월)
    반환: {"midterm_date": "MM/DD~MM/DD", "final_date": "MM/DD~MM/DD", "semester": "1학기"} 또는 빈 dict
    """
    if not os.getenv("NEIS_API_KEY"):
        return {}

    import datetime
    if month is None:
        month = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).month

    # 현재 학기 판단 및 조회 범위 설정
    if 3 <= month <= 8:
        semester = "1학기"
        start_date = f"{year}0301"
        end_date = f"{year}0831"
    else:
        semester = "2학기"
        start_date = f"{year}0901"
        end_date = f"{year + 1}0228"

    url = "https://open.neis.go.kr/hub/SchoolSchedule"
    params = {
        "KEY": os.getenv("NEIS_API_KEY"),
        "Type": "json", "pIndex": 1, "pSize": 500,
        "ATPT_OFCDC_SC_CODE": "F10", "SD_SCHUL_CODE": "7380292",
        "AA_FROM_YMD": start_date, "AA_TO_YMD": end_date
    }

    try:
        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=10)
            async with session.get(url, params=params, timeout=timeout) as resp:
                if resp.status != 200:
                    return {}
                try:
                    data = await resp.json()
                except aiohttp.ContentTypeError:
                    return {}

                if "SchoolSchedule" not in data:
                    return {}

                rows = data["SchoolSchedule"][1]["row"]

                # 시험 키워드 감지
                # 일반고: "중간고사", "기말고사"
                # 마이스터고(GSM): "1차 지필평가", "2차 지필평가"
                midterm_dates = []
                final_dates = []

                for r in rows:
                    name = r["EVENT_NM"]
                    date = r["AA_YMD"]  # YYYYMMDD

                    # ── 일반 패턴: 중간/기말 ──
                    if "중간" in name and ("고사" in name or "시험" in name or "평가" in name):
                        midterm_dates.append(date)
                    elif "기말" in name and ("고사" in name or "시험" in name or "평가" in name):
                        final_dates.append(date)
                    # ── 마이스터고 패턴: 1차/2차 지필평가 ──
                    elif "1차" in name and "지필" in name:
                        midterm_dates.append(date)
                    elif "2차" in name and "지필" in name:
                        final_dates.append(date)

                result = {"semester": semester}

                if midterm_dates:
                    midterm_dates.sort()
                    s = midterm_dates[0]
                    e = midterm_dates[-1]
                    s_fmt = f"{int(s[4:6]):02d}/{int(s[6:8]):02d}"
                    e_fmt = f"{int(e[4:6]):02d}/{int(e[6:8]):02d}"
                    result["midterm_date"] = f"{s_fmt}~{e_fmt}" if s != e else s_fmt

                if final_dates:
                    final_dates.sort()
                    s = final_dates[0]
                    e = final_dates[-1]
                    s_fmt = f"{int(s[4:6]):02d}/{int(s[6:8]):02d}"
                    e_fmt = f"{int(e[4:6]):02d}/{int(e[6:8]):02d}"
                    result["final_date"] = f"{s_fmt}~{e_fmt}" if s != e else s_fmt

                # semester만 있고 시험 날짜가 없으면 빈 dict 반환
                if len(result) <= 1:
                    return {}
                return result
    except Exception:
        return {}
