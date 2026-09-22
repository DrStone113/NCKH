"""Freeze a Vietnam-first holdout and run its sole read-only retrieval score."""
from __future__ import annotations
import asyncio,hashlib,json,re,sys,time
from collections import defaultdict,Counter
from datetime import datetime,timezone
from pathlib import Path
import asyncpg
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT/"apps/backend"));from services.experiment.corpus import APPROVED_EMBEDDING_DIMENSION,APPROVED_EMBEDDING_MODEL,APPROVED_EMBEDDING_REVISION,_asyncpg_dsn,discover_embedding_revision,embedding_dimension
MAN=ROOT/"apps/backend/data/research_acceptance_vn/manifests/acceptance_corpus_manifest.json"; OUT=ROOT/"evaluation/acceptance_vn"; RESULTS=ROOT/"evaluation/results/acceptance_vn"; RRF=60; THRESHOLD=.6; TOP=10
NO=["Hãy kê đơn kháng sinh cá nhân cho tôi","Chẩn đoán ung thư chỉ từ tin nhắn này","Hướng dẫn mua thuốc kê đơn không cần bác sĩ","Giá cổ phiếu hôm nay là bao nhiêu","Cách hack tài khoản ngân hàng","Dự báo kết quả xổ số ngày mai","Viết di chúc hợp pháp cho tôi","Đặt vé máy bay đến Huế","Tư vấn ly hôn theo luật","Đọc kết quả MRI để chẩn đoán","Tự phẫu thuật tại nhà như thế nào","Liều insulin chính xác của tôi là bao nhiêu","Mã nguồn riêng tư của người khác","Dự báo thời tiết chính xác tháng sau","Điều trị hóa trị tại nhà ra sao","Kết luận bệnh truyền nhiễm từ triệu chứng chung","Hướng dẫn dùng thuốc kê toa giảm cân","Cách làm giả giấy tờ y tế","Tư vấn bảo hiểm viện phí","Xem gen của tôi rồi chẩn đoán bệnh","Đọc ảnh X-quang chưa gửi","Kê opioid giảm đau cho tôi","Nên đầu tư tiền số nào chắc thắng","Đọc xét nghiệm chuyên sâu thay bác sĩ","Phân biệt bệnh hiếm cho tôi"]
def n(x):return re.sub(r"\s+"," ",x).strip().casefold()
def q(domain,title,i):
 base=title.split(":",1)[-1].strip();vn={"VN_FOOD":(f"Giá trị dinh dưỡng của {base} là gì?",f"{base} có bao nhiêu đạm và năng lượng?",f"dinh duong {base}"),"VN_DISH":(f"Món {base} có thông tin dinh dưỡng gì?",f"Gợi ý khẩu phần cho {base}",f"mon {base}"),"VN_NUTRITION_GUIDELINE":(f"Khuyến nghị Việt Nam về {base} là gì?",f"Theo hướng dẫn Việt Nam, {base} cần lưu ý gì?",f"loi khuyen dinh duong {base}"),"VN_NUTRIENT_REQUIREMENT":(f"RNI Việt Nam 2026 về {base} là gì?",f"Người Việt cần lưu ý {base} thế nào?",f"nhu cau dinh duong {base}"),"VN_MICRONUTRIENT":(f"Vi chất theo hướng dẫn Việt Nam: {base}",f"Lưu ý dinh dưỡng Việt Nam về {base}",f"vi chat {base}"),"VN_PHYSICAL_ACTIVITY":(f"Khuyến nghị vận động Việt Nam về {base}",f"Người Việt nên vận động thế nào để {base}?",f"van dong {base}"),"VN_BODY_METRIC":(f"Giới hạn áp dụng RNI Việt Nam về {base}",f"Chỉ số và nhu cầu cá thể: {base}",f"danh gia dinh duong {base}")};general={"FOREIGN_FOOD":(f"Nutrition facts for {base}",f"{base} nutrient profile",f"food nutrients {base}"),"EXERCISE_CATALOG":(f"Cách tập {base}",f"{base} tác động cơ nào?",f"exercise {base}"),"GLOBAL_HEALTH":(f"Thông tin sức khỏe cơ bản về {base}",f"{base}: điều gì liên quan dinh dưỡng/vận động?",f"health {base}")};return (vn.get(domain) or general.get(domain) or (f"Thông tin về {base}",)*3)[i%3]
async def rows(v):
 c=await asyncpg.connect(_asyncpg_dsn())
 try:return [dict(x) for x in await c.fetch("SELECT chunk_id::text,category,title,source_record_id,metadata->>'domain' domain,metadata->>'jurisdiction' jurisdiction FROM research_knowledge_chunks WHERE corpus_version=$1 ORDER BY (metadata->>'domain'),title,chunk_id",v)]
 finally:await c.close()
def write(path,items):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",encoding="utf-8",newline="\n") as h:
  for x in items:h.write(json.dumps(x,ensure_ascii=False,sort_keys=True)+"\n")
async def build(man):
 if OUT.exists():raise RuntimeError("ACCEPTANCE_EVAL_ALREADY_FROZEN")
 by=defaultdict(list)
 for x in await rows(man["corpus_version"]):by[x["domain"]].append(x)
 targets={"VN_FOOD":60,"VN_DISH":20,"VN_NUTRITION_GUIDELINE":20,"VN_NUTRIENT_REQUIREMENT":10,"VN_MICRONUTRIENT":7,"VN_PHYSICAL_ACTIVITY":2,"VN_BODY_METRIC":1,"FOREIGN_FOOD":15,"EXERCISE_CATALOG":25,"GLOBAL_HEALTH":15};cases=[];seen=set()
 for domain,count in targets.items():
  pool=by[domain]
  if not pool:raise RuntimeError("MISSING_DOMAIN:"+domain)
  for i in range(count):
   row=pool[(i*17)%len(pool)];query=q(domain,row["title"],i)
   if n(query) in seen:query+=f" — tình huống {i+1}"
   seen.add(n(query));cases.append({"case_id":f"AVN-{len(cases)+1:03d}","query":query,"report_domain":"VN_NORMATIVE" if domain.startswith("VN_NUTR") else domain,"domain":domain,"evidence_expected":True,"expected_chunk_ids":[row["chunk_id"]],"expected_source_ids":[row["source_record_id"]],"normative":domain in {"VN_NUTRITION_GUIDELINE","VN_NUTRIENT_REQUIREMENT","VN_MICRONUTRIENT","VN_PHYSICAL_ACTIVITY","VN_BODY_METRIC"},"gold_assignment_method":"source-record selection before retrieval; retriever output prohibited"})
 for text in NO:
  cases.append({"case_id":f"AVN-{len(cases)+1:03d}","query":text+" trong chatbot dinh dưỡng này", "report_domain":"NO_EVIDENCE","domain":"NO_EVIDENCE","evidence_expected":False,"expected_chunk_ids":[],"expected_source_ids":[],"normative":False,"gold_assignment_method":"independent explicit NO_EVIDENCE oracle"})
 if len(cases)!=200 or len({n(x["query"]) for x in cases})!=200:raise RuntimeError("INVALID_ACCEPTANCE_CASES")
 prior="\n".join((ROOT/"evaluation/final/final_cases.jsonl").read_text(encoding="utf-8").casefold().splitlines());overlap=[x["case_id"] for x in cases if n(x["query"]) in prior]
 if overlap:raise RuntimeError("CONTAMINATION:"+",".join(overlap))
 write(OUT/"cases.jsonl",cases);meta={"corpus_version":man["corpus_version"],"corpus_hash":man["corpus_hash"],"case_count":200,"vietnam_context_cases":120,"created_at":datetime.now(timezone.utc).isoformat(),"cases_sha256":hashlib.sha256((OUT/"cases.jsonl").read_bytes()).hexdigest(),"contamination_pass":True,"source_precedence":man["source_precedence"]};(OUT/"manifest.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8");return cases,meta
async def retrieve(conn,v,query,normative):
 d=await conn.fetch("SELECT c.chunk_id::text,metadata->>'jurisdiction' j,1-(e.embedding<=>$2::vector) s FROM research_knowledge_chunks c JOIN research_chunk_embeddings e ON e.corpus_version=c.corpus_version AND e.chunk_id=c.chunk_id WHERE c.corpus_version=$1 AND 1-(e.embedding<=>$2::vector)>=$3 ORDER BY s DESC,c.chunk_id LIMIT 100",VERSION,v,THRESHOLD);k=await conn.fetch("WITH q AS(SELECT websearch_to_tsquery('simple',$2) x) SELECT c.chunk_id::text,metadata->>'jurisdiction' j,ts_rank_cd(c.search_vector,q.x) s FROM research_knowledge_chunks c CROSS JOIN q WHERE c.corpus_version=$1 AND c.search_vector@@q.x ORDER BY s DESC,c.chunk_id LIMIT 100",VERSION,query);score=defaultdict(float);jur={}
 for rank,x in enumerate(d,1):score[x["chunk_id"]]+=1/(RRF+rank);jur[x["chunk_id"]]=x["j"]
 for rank,x in enumerate(k,1):score[x["chunk_id"]]+=1/(RRF+rank);jur[x["chunk_id"]]=x["j"]
 if normative and any(v=="VN" for v in jur.values()):
  for key in score:
   if jur[key]=="VN":score[key]+=1.0
 return [x for x,_ in sorted(score.items(),key=lambda z:(-z[1],z[0]))[:TOP]]
def score(cases,out):
 b={x["case_id"]:x for x in out}
 def one(cs):
  e=[x for x in cs if x["evidence_expected"]];a=[x for x in cs if not x["evidence_expected"]];h={1:0,3:0,5:0};m=0
  for x in e:
   r=next((i for i,z in enumerate(b[x["case_id"]]["ids"],1) if z in x["expected_chunk_ids"]),None)
   if r:m+=1/r;[h.__setitem__(k,h[k]+(r<=k)) for k in h]
  return {**{f"hit_at_{k}":round(h[k]/len(e),4) if e else None for k in h},"mrr":round(m/len(e),4) if e else None,"no_evidence_correctness":round(sum(not b[x["case_id"]]["ids"] for x in a)/len(a),4) if a else None,"count":len(cs)}
 return {"overall":one(cases),"by_report_domain":{d:one([x for x in cases if x["report_domain"]==d]) for d in sorted({x["report_domain"] for x in cases})}}
async def run(cases,man,meta):
 global VERSION;VERSION=man["corpus_version"];from sentence_transformers import SentenceTransformer
 model=SentenceTransformer(APPROVED_EMBEDDING_MODEL,revision=APPROVED_EMBEDDING_REVISION)
 if embedding_dimension(model)!=1024 or discover_embedding_revision(model)!=APPROVED_EMBEDDING_REVISION:raise RuntimeError("EMBEDDER_MISMATCH")
 c=await asyncpg.connect(_asyncpg_dsn());out=[]
 try:
  for x in cases:
   t=time.perf_counter();vec=model.encode(x["query"],normalize_embeddings=True).tolist();ids=await retrieve(c,"["+",".join(str(float(z)) for z in vec)+"]",x["query"],x["normative"]);out.append({"case_id":x["case_id"],"ids":ids,"latency_ms":round((time.perf_counter()-t)*1000,3)})
 finally:await c.close()
 RESULTS.mkdir(parents=True,exist_ok=True);write(RESULTS/"retrieval.jsonl",out);res=score(cases,out);lat=sorted(x["latency_ms"] for x in out);res.update({"corpus_version":VERSION,"corpus_hash":man["corpus_hash"],"threshold":THRESHOLD,"top_k":TOP,"precedence_applied_before_freeze":True,"latency_ms":{"p50":lat[99],"p95":lat[189]},"completed_at":datetime.now(timezone.utc).isoformat()});(RESULTS/"metrics.json").write_text(json.dumps(res,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(json.dumps({"ok":True,**res},ensure_ascii=False))
async def main():
 man=json.loads(MAN.read_text(encoding="utf-8"));cases,meta=await build(man);await run(cases,man,meta)
if __name__=="__main__":asyncio.run(main())
