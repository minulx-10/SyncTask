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
