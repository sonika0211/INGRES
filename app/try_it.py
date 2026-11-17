import time

from answer import make_answer
from llm import llm
from text2sql import DB_PATH, ask
from validator import SchemaInfo

t0 = time.time()
schema = SchemaInfo(DB_PATH)
print(f"Schema loaded in {time.time() - t0:.1f}s (one-time)")

llm_time = 0.0


def timed_llm(system, prompt):
    global llm_time
    t = time.time()
    out = llm(system, prompt)
    dt = time.time() - t
    llm_time += dt
    print(f"  [LLM call: {dt:.1f}s]")
    return out


while True:
    q = input("\nQuestion (blank to quit): ").strip()
    if not q:
        break
    llm_time = 0.0
    start = time.time()
    r = ask(q, timed_llm, schema)
    a = make_answer(q, r, timed_llm)
    total = time.time() - start

    print("\nANSWER:", a["answer"])
    print(f"verified: {a['verified']}" + (f"  flags: {a['flags']}" if a["flags"] else ""))
    if a["sql"]:
        print("SQL   :", a["sql"], f"(SQL tries: {r.get('tries', '-')})")
    if a["table"] is not None and not a["table"].empty:
        print(a["table"].head(10).to_string(index=False))
    print(f"Total {total:.1f}s = LLM {llm_time:.1f}s + everything else {total - llm_time:.1f}s")