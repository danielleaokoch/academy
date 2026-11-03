#!/usr/bin/env python3
"""Eleva Academy discovery v1: fontes oficiais RSS, sem chave paga.
Candidatos = metadados, não licença nem reprodução verificadas.
"""
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

CHANNELS = [
    ("CS50 (Harvard)", "UCcabW7890RKJzL968QWEykA", "en"),
    ("freeCodeCamp.org", "UC8butISFwT-Wl7EV0hUK0BQ", "en"),
    ("UNIVESP TV", "UCBL2tfrwhEhX52Dze_aO3zA", "pt-BR"),
]
SKILLS = {
    "lideranca": ["liderança", "lideranca", "leadership", "people management", "gestão de pessoas", "gestao de pessoas"],
    "estrategia": ["estratégia", "estrategia", "strategic", "strategy", "planejamento", "planning", "business"],
    "financas": ["finanças", "financas", "finance", "financial", "orçamento", "budget", "cash flow"],
    "dados": ["dados", "data analysis", "data science", "estatística", "estatistica", "statistics", "pandas", "power bi"],
    "ia": ["inteligência artificial", "inteligencia artificial", "artificial intelligence", "generative ai", "machine learning", "llm", "agents", "ai agents"],
    "programacao": ["programação", "programacao", "programming", "python", "javascript", "algoritmo", "algorithm", "coding"],
    "marketing": ["marketing", "growth", "seo", "campaign", "ads", "marca", "branding"]
}
NEGATIVE = ["trailer", "shorts", "#shorts", "teaser", "live stream", "podcast", "behind the scenes", "entrevista"]
ATOM = "{http://www.w3.org/2005/Atom}"
YT = "{http://www.youtube.com/xml/schemas/2015}"
OUT = Path("data/discovered.json")

def score(title, description=""):
    t = (title + " " + description[:280]).lower()
    found = []
    points = 0
    for skill, words in SKILLS.items():
        matches = sum(w in t for w in words)
        if matches:
            found.append(skill)
            points += min(matches, 3) * 15
    if any(x in title.lower() for x in NEGATIVE):
        points -= 80
    if any(x in title.lower() for x in ["aula ", "curso ", "lecture", "tutorial", "course", "introdução", "introduction", "learn "]):
        points += 12
    return points, found

def get_feed(provider, channel_id, language):
    url = "https://www.youtube.com/feeds/videos.xml?channel_id=" + channel_id
    req = urllib.request.Request(url, headers={"User-Agent": "ElevaAcademyLab/1.0 (public feed; educational discovery)"})
    with urllib.request.urlopen(req, timeout=18) as resp:
        xml = resp.read(1500000)
    root = ET.fromstring(xml)
    found = []
    for entry in root.findall(ATOM + "entry"):
        video_id = (entry.findtext(YT + "videoId") or "").strip()
        title = (entry.findtext(ATOM + "title") or "").strip()
        published = (entry.findtext(ATOM + "published") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) or not title:
            continue
        relevance, skills = score(title)
        if relevance < 15 or not skills:
            continue
        found.append({
            "id": "yt:" + video_id,
            "videoId": video_id,
            "title": title[:160],
            "provider": provider,
            "sourceType": "youtube_official_channel_rss",
            "sourceUrl": "https://www.youtube.com/watch?v=" + video_id,
            "embedUrl": "https://www.youtube-nocookie.com/embed/" + video_id,
            "languageHint": language,
            "published": published,
            "skills": skills,
            "score": relevance,
            "verification": "candidate_unverified_embed_and_licensing",
        })
    return found


def get_microsoft_learn():
    """Catálogo oficial público: metadados somente, sem direito de incorporar aulas."""
    url = "https://learn.microsoft.com/api/catalog/?locale=pt-br&type=modules,learningPaths"
    req = urllib.request.Request(url, headers={"User-Agent": "ElevaAcademyLab/1.0"})
    with urllib.request.urlopen(req, timeout=35) as resp:
        # Resposta pode ser extensa. Limitamos a memória e o corpo.
        raw = resp.read(35000000)
        if resp.read(1):
            raise ValueError("Catálogo maior que o limite de segurança")
    catalog = json.loads(raw.decode("utf-8"))
    found = []
    for row in (catalog.get("modules") or []) + (catalog.get("learningPaths") or []):
        uid = str(row.get("uid", ""))
        title = str(row.get("title", "")).strip()
        link = str(row.get("url", ""))
        if not uid or not title or not link.startswith("https://learn.microsoft.com/"):
            continue
        relevance, skills = score(title, re.sub("<[^>]+>", " ", str(row.get("summary", ""))))
        if relevance < 25 or not skills:
            continue
        found.append({
            "id": "mslearn:" + uid,
            "title": title[:160],
            "provider": "Microsoft Learn",
            "sourceType": "microsoft_learn_catalog_api",
            "sourceUrl": link,
            "embedUrl": None,
            "playback": "external_only_no_embeddable_player_verified",
            "languageHint": str(row.get("locale") or "pt-br"),
            "published": str(row.get("last_modified") or ""),
            "durationMinutes": row.get("duration_in_minutes"),
            "skills": skills,
            "score": relevance + min(float(row.get("popularity") or 0), 1) * 15,
            "verification": "official_catalog_metadata_not_licensed_for_embedding",
        })
    return sorted(found, key=lambda x: -x["score"])[:120]

def run():
    old = {}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    discovered = {}
    errors = []
    successes = []
    for name, cid, lang in CHANNELS:
        try:
            rows = get_feed(name, cid, lang)
            successes.append({"provider": name, "items": len(rows)})
            for row in rows:
                discovered[row["id"]] = row
        except Exception as e:
            errors.append({"provider": name, "error": type(e).__name__ + ": " + str(e)[:150]})
            print("Aviso:", name, errors[-1]["error"], file=sys.stderr)
    try:
        learn = get_microsoft_learn()
        successes.append({"provider": "Microsoft Learn", "items": len(learn), "playback": "external_only"})
        for row in learn:
            discovered[row["id"]] = row
    except Exception as e:
        errors.append({"provider": "Microsoft Learn", "error": type(e).__name__ + ": " + str(e)[:150]})
        print("Aviso:", "Microsoft Learn", errors[-1]["error"], file=sys.stderr)

    # Nunca zerar um catálogo anterior quando todas as fontes estiverem indisponíveis.
    if not successes and old.get("items"):
        print("Fontes indisponíveis; mantendo catálogo anterior")
        return
    items = sorted(discovered.values(), key=lambda x: (-x["score"], x["title"]))[:150]
    payload = {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "method": "official_youtube_channel_atom_feeds_and_microsoft_learn_catalog_api",
        "coverage": "YouTube recent uploads when accessible; Microsoft Learn modules and learning paths; metadata only",
        "readyForPaidUse": False,
        "sources": successes,
        "errors": errors,
        "items": items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Descobertos {len(items)} candidatos de {len(successes)} fontes; {len(errors)} erros.")

if __name__ == "__main__":
    run()
