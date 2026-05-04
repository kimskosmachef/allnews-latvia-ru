import requests
from bs4 import BeautifulSoup

url = "https://rus.tvnet.lv/8464543/foto-vrucheny-ordena-treh-zvezd"
r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(r.text, "html.parser")
for a in soup.find_all("a", itemprop="item", href=True):
    if "/section/" in a["href"]:
        print(a["href"])