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
