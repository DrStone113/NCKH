"""Read-only integrity verification for offline-acceptance-vn."""
from __future__ import annotations
import asyncio,hashlib,json,sys
from pathlib import Path
from sqlalchemy import text
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT/"apps/backend"));from db.database import AsyncSessionLocal
M=ROOT/"apps/backend/data/research_acceptance_vn/manifests/acceptance_corpus_manifest.json"
def canon(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()
async def main():
 m=json.loads(M.read_text(encoding="utf-8"));h=m.pop("manifest_hash");assert hashlib.sha256(canon(m)).hexdigest()==h,"MANIFEST_HASH_MISMATCH"
 async with AsyncSessionLocal() as db:
  rows=(await db.execute(text("SELECT chunk_id::text,category,title,content,metadata,source_type,source_name,source_url,source_record_id,dataset_file,dataset_hash,content_hash,is_dynamic FROM research_knowledge_chunks WHERE corpus_version=:v ORDER BY chunk_id"),{"v":m["corpus_version"]})).mappings().all();ec=int((await db.execute(text("SELECT count(*) FROM research_chunk_embeddings WHERE corpus_version=:v"),{"v":m["corpus_version"]})).scalar_one());n=(await db.execute(text("SELECT sqrt(-(embedding <#> embedding)) FROM research_chunk_embeddings WHERE corpus_version=:v LIMIT 20"),{"v":m["corpus_version"]})).scalars().all()
 actual=hashlib.sha256(canon([dict(x) for x in rows])).hexdigest();out={"ok":len(rows)==ec==m["record_count"] and actual==m["corpus_hash"] and all(abs(float(x)-1)<1e-3 for x in n),"corpus_version":m["corpus_version"],"chunks":len(rows),"embeddings":ec,"corpus_hash":m["corpus_hash"],"actual_hash":actual,"sample_l2_norms":[round(float(x),6) for x in n]};print(json.dumps(out,ensure_ascii=False));return 0 if out["ok"] else 1
if __name__=="__main__":raise SystemExit(asyncio.run(main()))
