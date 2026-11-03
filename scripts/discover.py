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
    # Nunca zerar um catálogo anterior quando todas as fontes estiverem indisponíveis.
    if not successes and old.get("items"):
        print("Fontes indisponíveis; mantendo catálogo anterior")
        return
    items = sorted(discovered.values(), key=lambda x: (-x["score"], x["title"]))[:60]
    payload = {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "method": "official_youtube_channel_atom_feeds",
        "coverage": "only_recent_uploads; no comprehensive search; metadata only",
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
