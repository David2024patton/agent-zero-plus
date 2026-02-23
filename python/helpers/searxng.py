import aiohttp
from python.helpers import runtime

URL = "http://localhost:55510/search"

# Top search engines for maximum coverage
DEFAULT_ENGINES = "google,bing,duckduckgo,brave,startpage,mojeek,qwant,yahoo,yandex,wikipedia"

async def search(query: str, categories: str = "", engines: str = "", count: int = 20, pageno: int = 1):
    return await runtime.call_development_function(
        _search, query=query, categories=categories, engines=engines, count=count, pageno=pageno
    )

async def _search(query: str, categories: str = "", engines: str = "", count: int = 20, pageno: int = 1):
    params = {
        "q": query,
        "format": "json",
        "pageno": str(pageno),
    }
    
    # Use specified engines or default top engines
    if engines:
        params["engines"] = engines
    else:
        params["engines"] = DEFAULT_ENGINES
    
    # Optional category filter (general, images, news, etc.)
    if categories:
        params["categories"] = categories
    
    async with aiohttp.ClientSession() as session:
        async with session.post(URL, data=params) as response:
            data = await response.json()
    
    # Trim results to requested count
    if "results" in data and len(data["results"]) > count:
        data["results"] = data["results"][:count]
    
    return data
