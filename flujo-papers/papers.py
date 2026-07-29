#!/usr/bin/env python3
"""
papers.py — Revisión de literatura para fertilidad, con datos REALES.

Dado un tema clínico, trae los estudios MÁS CITADOS de un periodo desde PubMed
(NCBI) y sus conteos de citación reales desde iCite (NCBI). Sin inventar nada:
cada resultado lleva su PMID, DOI y enlace verificable.

Pensado como:
  1) el "regalo" que se comparte en la comunidad SEF (aporte de valor real),
  2) la demo grabable del reel A1 "Papers al día" (Código AdrIA).

Uso:
  python3 papers.py "sperm DNA fragmentation IVF pregnancy" --years 2019-2026 --n 8
  python3 papers.py "endometrial receptivity implantation" --n 10 --json out.json

Notas:
  - No requiere API key. Con una NCBI API key (gratis) sube el límite de peticiones:
    export NCBI_API_KEY=xxxx   (opcional)
  - El "TL;DR clínico" que se muestra es el ABSTRACT REAL recortado. La lectura /
    implicación clínica la pone el profesional (esa es justo la regla anti-humo:
    la IA busca y ordena; el criterio lo pone quien sabe).
  - Solo dependencias estándar (urllib). Nada que instalar.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ICITE = "https://icite.od.nih.gov/api/pubs"
UA = "codigo-adria-papers/1.0 (revision-literatura-fertilidad)"


def _get(url, tries=3, pause=0.5):
    """GET con reintentos suaves (NCBI corta si vas rápido)."""
    key = os.environ.get("NCBI_API_KEY")
    if key:
        url += ("&" if "?" in url else "?") + "api_key=" + key
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE401
            last = e
            time.sleep(pause * (i + 1))
    raise SystemExit(f"[ERROR] NCBI no responde ({last}). Reintenta en un momento.")


def esearch(topic, years, retmax):
    term = topic
    if years:
        lo, hi = years
        term += f" AND ({lo}:{hi}[dp])"
    q = urllib.parse.urlencode(
        {"db": "pubmed", "term": term, "retmax": retmax, "retmode": "json", "sort": "relevance"}
    )
    data = json.loads(_get(f"{EUTILS}/esearch.fcgi?{q}"))
    return data.get("esearchresult", {}).get("idlist", [])


def esummary(pmids):
    if not pmids:
        return {}
    q = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(pmids), "retmode": "json"})
    data = json.loads(_get(f"{EUTILS}/esummary.fcgi?{q}"))
    return data.get("result", {})


def icite_counts(pmids):
    """Conteos de citación reales (iCite/NIH). Devuelve {pmid: n_citas}."""
    out = {}
    for i in range(0, len(pmids), 200):
        chunk = pmids[i : i + 200]
        q = urllib.parse.urlencode({"pmids": ",".join(chunk)})
        try:
            data = json.loads(_get(f"{ICITE}?{q}"))
            for row in data.get("data", []):
                out[str(row.get("pmid"))] = row.get("citation_count", 0) or 0
        except SystemExit:
            pass  # si iCite falla, seguimos sin conteos (no rompemos la demo)
        time.sleep(0.34)
    return out


def efetch_abstracts(pmids):
    """Abstract real por PMID (texto plano)."""
    if not pmids:
        return {}
    q = urllib.parse.urlencode(
        {"db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "text"}
    )
    raw = _get(f"{EUTILS}/efetch.fcgi?{q}")
    # Cada registro se separa por 2+ líneas en blanco. Dentro, el abstract es el
    # párrafo de texto más largo que NO es metadato (cita, autores, afiliación, DOI…).
    blocks = re.split(r"\n\n\n+", raw.strip())
    out = {}
    meta = re.compile(
        r"^(Author information:|DOI:|PMID:|©|Copyright|Comment in|Update in|Erratum|"
        r"Conflict of interest|\d+\.\s)", re.I
    )
    for pmid, block in zip(pmids, blocks):
        paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\n+", block)]
        cand = [p for p in paras if len(p.split()) >= 25 and not meta.match(p)]
        out[pmid] = max(cand, key=len) if cand else ""
    return out


def short(txt, n=320):
    txt = re.sub(r"\s+", " ", txt or "").strip()
    return txt if len(txt) <= n else txt[: txt.rfind(" ", 0, n)] + "…"


def authors_str(uids_entry):
    a = uids_entry.get("authors", []) or []
    names = [x.get("name", "") for x in a if x.get("name")]
    if not names:
        return "—"
    return names[0] + (" et al." if len(names) > 1 else "")


def main():
    ap = argparse.ArgumentParser(description="Top papers citados de PubMed para un tema.")
    ap.add_argument("topic", help="tema clínico (en inglés funciona mejor en PubMed)")
    ap.add_argument("--years", help="rango, p.ej. 2019-2026", default="2019-2026")
    ap.add_argument("--n", type=int, default=8, help="cuántos mostrar (top citados)")
    ap.add_argument("--pool", type=int, default=60, help="candidatos a evaluar antes de ordenar")
    ap.add_argument("--json", help="guarda el resultado en este fichero JSON")
    args = ap.parse_args()

    years = None
    if args.years:
        m = re.match(r"(\d{4})-(\d{4})", args.years)
        if m:
            years = (m.group(1), m.group(2))

    print(f"\n🔎  Buscando en PubMed: «{args.topic}»  ({args.years})\n", file=sys.stderr)
    pmids = esearch(args.topic, years, args.pool)
    if not pmids:
        raise SystemExit("[SIN RESULTADOS] Prueba otro término (mejor en inglés).")

    counts = icite_counts(pmids)
    summ = esummary(pmids)

    ranked = sorted(pmids, key=lambda p: counts.get(p, 0), reverse=True)[: args.n]
    abstracts = efetch_abstracts(ranked)

    results = []
    for rank, pmid in enumerate(ranked, 1):
        s = summ.get(pmid, {})
        doi = ""
        for aid in s.get("articleids", []) or []:
            if aid.get("idtype") == "doi":
                doi = aid.get("value", "")
        results.append(
            {
                "rank": rank,
                "pmid": pmid,
                "title": s.get("title", "").strip("."),
                "year": (s.get("pubdate", "") or "")[:4],
                "journal": s.get("fulljournalname", "") or s.get("source", ""),
                "authors": authors_str(s),
                "citations": counts.get(pmid, 0),
                "doi": doi,
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "tldr": short(abstracts.get(pmid, "")),
            }
        )

    # Salida en pantalla (bonita para grabar el reel)
    print(f"📚  TOP {len(results)} estudios más citados — «{args.topic}»")
    print(f"    Fuente: PubMed + iCite (NIH) · citas reales · {args.years}\n")
    for r in results:
        print(f"#{r['rank']}  🔹 {r['citations']} citas · {r['year']} · {r['journal']}")
        print(f"    {r['title']}")
        print(f"    {r['authors']}   ·   {r['pubmed_url']}")
        if r["doi"]:
            print(f"    doi:{r['doi']}")
        print(f"    TL;DR (abstract real): {r['tldr']}")
        print()

    print("ℹ️  La IA ha buscado y ordenado por citación real. La implicación clínica")
    print("    la pones tú: ese es el trabajo que no se delega.\n")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"💾  Guardado en {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
