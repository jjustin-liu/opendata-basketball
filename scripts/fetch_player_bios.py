import json, re, urllib.request, concurrent.futures
from pathlib import Path

s = (
    urllib.request.urlopen(
        "https://www.acb.com/es/liga/equipos/asisa-joventut-8/plantilla?editionId=90",
        timeout=25,
    )
    .read()
    .decode()
)
paths = sorted(set(re.findall(r"/es/liga/equipos/[a-z0-9-]+", s)))
paths += [
    "/es/liga/equipos/coviran-granada-592",
    "/es/liga/equipos/dreamland-gran-canaria-5",
]


def fetch(path):
    url = "https://www.acb.com" + path + "/plantilla?editionId=90"
    try:
        html = urllib.request.urlopen(url, timeout=25).read().decode()
        chunks = []
        for m in re.finditer(
            r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html
        ):
            chunks.append(json.loads(m[1]))
        text = "".join(chunks)
        out = []
        decoder = json.JSONDecoder()
        for m in re.finditer(r'\{"player":\{', text):
            try:
                row, _ = decoder.raw_decode(text[m.start() :])
                if "height" in row and "gameRole" in row["player"]:
                    p = row["player"]
                    out.append(
                        dict(
                            acbId=p["id"],
                            name=p.get("nickname"),
                            first=p.get("nicknameFirstName"),
                            last=p.get("nicknameLastName"),
                            fullName=p.get("firstName", "")
                            + " "
                            + p.get("lastName", ""),
                            position=p["gameRole"],
                            heightCm=row["height"],
                            source=url,
                        )
                    )
            except (ValueError, KeyError):
                pass
        return out
    except Exception as e:
        print(path, type(e).__name__)
        return []


with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
    rows = [r for group in ex.map(fetch, paths) for r in group]
unique = {r["acbId"]: r for r in rows}
Path("data/player_bios_acb.json").write_text(
    json.dumps(list(unique.values()), ensure_ascii=False, indent=2)
)
print("Bios", len(unique))
