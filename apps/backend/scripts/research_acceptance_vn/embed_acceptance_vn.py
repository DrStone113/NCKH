"""Embed and freeze the one Vietnam-first acceptance corpus."""
from __future__ import annotations
import asyncio, hashlib, importlib.metadata, json, platform, sys, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import asyncpg

ROOT=Path(__file__).resolve().parents[4]; BACKEND=ROOT/"apps/backend"; sys.path.insert(0,str(BACKEND))
from services.experiment.corpus import APPROVED_EMBEDDING_DIMENSION, APPROVED_EMBEDDING_MODEL, APPROVED_EMBEDDING_REVISION, NORMALIZATION_BEHAVIOR, _asyncpg_dsn, discover_embedding_revision, embedding_dimension
DATA=BACKEND/"data/research_acceptance_vn"; CANDIDATE=DATA/"manifests/acceptance_candidate.jsonl"; CANDIDATE_MANIFEST=DATA/"manifests/acceptance_candidate_manifest.json"; REGISTRY=DATA/"source_registry.json"; FINAL=DATA/"manifests/acceptance_corpus_manifest.json"
def canon(x:Any)->bytes:return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=str).encode()
def sha(x:bytes)->str:return hashlib.sha256(x).hexdigest()
def stored(r:dict[str,Any],version:str,registry_hash:str)->dict[str,Any]:
    meta={k:v for k,v in r.items() if k not in {"chunk_id","category","title","content","content_hash"}};meta.update({"corpus_version":version,"is_dynamic":False,"source_registry_hash":registry_hash})
    return {"chunk_id":r["chunk_id"],"category":r["category"],"title":r["title"],"content":r["content"],"metadata":meta,"source_type":"acceptance_vn_normalized","source_name":r["publisher"],"source_url":r["source_url"],"source_record_id":r["source_record_id"],"dataset_file":r["source_id"],"dataset_hash":registry_hash,"content_hash":r["content_hash"],"is_dynamic":False}
async def main()->int:
    if FINAL.exists():raise RuntimeError("ACCEPTANCE_ALREADY_FROZEN")
    candidate=[json.loads(x) for x in CANDIDATE.read_text(encoding="utf-8").splitlines() if x]; candidate_manifest=json.loads(CANDIDATE_MANIFEST.read_text(encoding="utf-8"))
    if not candidate_manifest["audit"]["pass"]:raise RuntimeError("CANDIDATE_AUDIT_FAILED")
    version=f"offline-acceptance-vn-{len(candidate)}"; registry=json.loads(REGISTRY.read_text(encoding="utf-8"));registry["registry_status"]="FROZEN_FOR_"+version;registry_hash=sha(canon(registry));payloads=[stored(r,version,registry_hash) for r in sorted(candidate,key=lambda x:x["chunk_id"])]; corpus_hash=sha(canon(payloads))
    from sentence_transformers import SentenceTransformer
    import torch
    start=time.perf_counter();model=SentenceTransformer(APPROVED_EMBEDDING_MODEL,revision=APPROVED_EMBEDDING_REVISION)
    if embedding_dimension(model)!=APPROVED_EMBEDDING_DIMENSION or discover_embedding_revision(model)!=APPROVED_EMBEDDING_REVISION:raise RuntimeError("EMBEDDING_IDENTITY_MISMATCH")
    vectors=model.encode([x["content"] for x in candidate],batch_size=128,show_progress_bar=True,normalize_embeddings=True)
    if len(vectors)!=len(candidate) or any(len(v)!=1024 for v in vectors) or any(abs(sum(float(x)*float(x) for x in v)-1)>1e-3 for v in vectors[:100]):raise RuntimeError("EMBEDDING_OUTPUT_INVALID")
    manifest={"schema_version":"acceptance-vn-manifest-1","corpus_version":version,"record_count":len(candidate),"corpus_hash":corpus_hash,"candidate_sha256":sha(CANDIDATE.read_bytes()),"source_registry_hash":registry_hash,"embedding_model":APPROVED_EMBEDDING_MODEL,"embedding_model_revision":APPROVED_EMBEDDING_REVISION,"embedding_dimension":1024,"sentence_transformers_version":importlib.metadata.version("sentence-transformers"),"normalization_behavior":NORMALIZATION_BEHAVIOR,"source_precedence":candidate_manifest["source_precedence"],"domain_counts":dict(sorted(Counter(x["domain"] for x in candidate).items())),"jurisdiction_counts":dict(sorted(Counter(x["jurisdiction"] for x in candidate).items())),"candidate_audit":candidate_manifest["audit"],"created_at":datetime.now(timezone.utc).isoformat(),"build_duration_seconds":round(time.perf_counter()-start,3),"hardware":{"device":str(getattr(model,"device","unknown")),"cuda":torch.cuda.is_available(),"batch_size":128},"previous_final_preserved":True,"frozen":True}
    manifest["manifest_hash"]=sha(canon(manifest))
    from db.database import apply_migrations
    await apply_migrations();conn=await asyncpg.connect(_asyncpg_dsn())
    try:
      if await conn.fetchval("SELECT 1 FROM research_corpus_manifests WHERE corpus_version=$1 OR corpus_hash=$2",version,corpus_hash):raise RuntimeError("ACCEPTANCE_VERSION_OR_HASH_EXISTS")
      async with conn.transaction():
       await conn.execute("INSERT INTO research_corpus_manifests (corpus_version,corpus_hash,manifest,created_at) VALUES ($1,$2,$3::jsonb,$4)",version,corpus_hash,json.dumps(manifest,ensure_ascii=False),datetime.fromisoformat(manifest["created_at"]))
       await conn.executemany("INSERT INTO research_knowledge_chunks (corpus_version,chunk_id,category,title,content,metadata,source_type,source_name,source_url,source_record_id,dataset_file,dataset_hash,content_hash,is_dynamic) VALUES ($1,$2::uuid,$3,$4,$5,$6::jsonb,$7,$8,$9,$10,$11,$12,$13,FALSE)",[(version,x["chunk_id"],x["category"],x["title"][:500],x["content"],json.dumps(x["metadata"],ensure_ascii=False),x["source_type"],x["source_name"],x["source_url"],x["source_record_id"],x["dataset_file"],x["dataset_hash"],x["content_hash"]) for x in payloads])
       await conn.executemany("INSERT INTO research_chunk_embeddings (corpus_version,chunk_id,embedding) VALUES ($1,$2::uuid,$3::vector)",[(version,x["chunk_id"],"["+",".join(str(float(v)) for v in vector)+"]") for x,vector in zip(candidate,vectors)])
    finally:await conn.close()
    REGISTRY.write_text(json.dumps(registry,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8");FINAL.write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"ok":True,"corpus_version":version,"record_count":len(candidate),"corpus_hash":corpus_hash,"manifest_hash":manifest["manifest_hash"]},ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(asyncio.run(main()))
