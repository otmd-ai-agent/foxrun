"""Independent black-box evaluation; run after the documented isolated install."""
import concurrent.futures, hashlib, json, os, pathlib, sqlite3, subprocess, sys, time
ROOT=pathlib.Path(__file__).resolve().parent
SYSTEM=ROOT/'system'; WS=ROOT/'portfolio/sample-shop'; LOG=ROOT/'logs'
ENV=dict(os.environ,FOXRUN_HOME=str(SYSTEM),FOXRUN_PORTFOLIO=str(ROOT/'portfolio'),FOXRUN_PERSON='evaluator')
results=[]; commands=[]
def run(path,*args):
 t=time.monotonic(); p=subprocess.run([sys.executable,str(SYSTEM/path),*map(str,args)],env=ENV,capture_output=True,text=True,timeout=90)
 commands.append(dict(command=[path,*map(str,args)],code=p.returncode,stdout=p.stdout,stderr=p.stderr,seconds=time.monotonic()-t)); return p
def check(name,ok,detail=''):
 results.append(dict(case=name,passed=bool(ok),detail=detail))
def work(*args): return run('work/work.py','--workspace','sample-shop','--receipt-root',WS,*args)
fields=['--problem','Delivery needs checking','--job-when','Delivery arrives','--job-want','Check inventory','--job-so','Stock is accurate','--body','Count three units','--acceptance','Three units counted','--context','Synthetic independent eval','--where','STATE.md']
p=work('create','--title','Invalid incomplete task','--by','evaluator'); check('missing acceptance rejected',p.returncode!=0)
p=work('create','--title','Independent inventory check','--by','evaluator',*fields); task=p.stdout.strip(); check('complete task created',p.returncode==0,task)
p=run('foxrun.py','start','--workspace','sample-shop'); check('fresh process sees task',task in p.stdout and 'Independent inventory check' in p.stdout)
p=work('accept',task,'--by','reviewer'); check('accept without completion rejected',p.returncode!=0)
p=work('done',task,'--by','worker','--proof',ROOT/'missing-proof.txt','--note','Count complete'); check('missing proof rejected',p.returncode!=0)
proof=WS/'inventory-proof.txt'; proof.write_text('Synthetic inventory: expected 3 units; observed 3 units.\n')
p=work('done',task,'--by','worker','--proof','inventory-proof.txt','--note','Counted three units'); check('completion with proof enters review',p.returncode==0,p.stdout+p.stderr)
p=work('accept',task,'--by','worker'); check('finisher cannot self-accept',p.returncode!=0,p.stdout+p.stderr)
p=work('accept',task,'--by','reviewer'); check('independent reviewer accepts',p.returncode==0,p.stdout+p.stderr)
p=work('show',task); check('completed status persisted','done' in p.stdout,p.stdout)
p=work('lesson-add','--rule','EVAL: count each delivery before accepting stock','--source','task:'+task,'--by','reviewer'); check('lesson stored',p.returncode==0)
p=run('foxrun.py','start','--workspace','sample-shop'); check('new session reads lesson','EVAL: count each delivery' in p.stdout)
p=run('foxrun.py','start','--workspace','no-such-workspace'); check('unknown workspace refused',p.returncode!=0)
p=run('foxrun.py','hookup','--runtime','both','--runtime-home',ROOT/'runtime'); check('hookup idempotent',p.returncode==0 and 'Nothing changed' in p.stdout,p.stdout)
def newrun(i): return run('memory/runs.py','new','--task',task,'--seat','worker','--what','parallel-probe')
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: runs=list(pool.map(newrun,range(16)))
paths=[p.stdout.strip() for p in runs]; check('16 concurrent run folders unique',all(p.returncode==0 for p in runs) and len(set(paths))==16)
local=SYSTEM/'config/eval.local.md'; local.write_text('Synthetic personal setting; preserve this.\n')
personal=WS/'notes/eval-preserve.md'; personal.write_text('Synthetic workspace note; preserve this.\n')
before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in (local,personal)]
p=run('foxrun.py','update','--source','/workspace/foxrun','--home',SYSTEM); check('same-version update succeeds',p.returncode==0,p.stdout[-600:]+p.stderr)
check('update preserves local and workspace bytes',before==[hashlib.sha256(p.read_bytes()).hexdigest() for p in (local,personal)])
p=work('show',task); check('update preserves task',p.returncode==0 and 'Independent inventory check' in p.stdout and 'done' in p.stdout)
p=run('foxrun.py','doctor'); check('post-update doctor clean',p.returncode==0 and 'Doctor: 0 failed' in p.stdout)
(LOG/'independent-commands.json').write_text(json.dumps(commands,indent=2)); (LOG/'independent-results.json').write_text(json.dumps(results,indent=2))
for r in results: print(('PASS' if r['passed'] else 'FAIL'),r['case'],r['detail'][:200])
sys.exit(int(not all(r['passed'] for r in results)))
