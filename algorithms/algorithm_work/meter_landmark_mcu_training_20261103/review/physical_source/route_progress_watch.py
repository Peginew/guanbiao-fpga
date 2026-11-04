"""Read-only bounded-progress observations; never stops or changes a process."""
from pathlib import Path
import argparse,datetime,json,re
from audit_synth import TASK,HERE,read,write,ref

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--route-receipt',type=Path,default=TASK/'physical/latest_route.json')
    args=ap.parse_args()
    route=read(args.route_receipt);log=Path(route['run'])/'console.log'
    variant='guided_'if'guided_'in args.route_receipt.name else'literal_'if'literal_'in args.route_receipt.name else''
    destination=HERE/(variant+'route_progress_observation.json')
    text=log.read_text(errors='replace');now=datetime.datetime.now(datetime.timezone.utc)
    phases=list(re.finditer(r'^PHY-1001 : Stage (2\.5\.(\d+)\.4) \| Rip-up And ReRoute\s*$',text,re.M))
    out=dict(route_receipt=ref(args.route_receipt),run=route['run'],observed_UTC=now.isoformat(),
        latest_state=route['state'],completion_observed=route['state']!='RUNNING'or bool(re.search(r'^(?:UI_ROUTE_COMPLETE|(?:GUIDED_)?LITERAL_CONTRACT_FINAL_COMPLETE)\s*$',text,re.M)),
        no_process_actions=True)
    if phases:
        stage=phases[-1][1];block=text[phases[-1].end():]
        block=block.split('End Stage '+stage,1)[0]
        rows=[dict(iteration=int(i),over=int(n),iteration_seconds=float(s))for i,n,s in re.findall(
            r'^PHY-1001 : Iter (\d+):.*?over cnt = (\d+).*?time\(s\) = ([\d.]+)\s*$',block,re.M)]
        if rows:
            best_index=0
            for j in range(1,len(rows)):
                if rows[j]['over']<rows[best_index]['over']:best_index=j
            best=rows[best_index];seconds=sum(r['iteration_seconds']for r in rows[best_index+1:]);count=len(rows)-best_index-1
            previous=destination;first=now
            if previous.exists():
                old=read(previous)
                if old.get('stage')==stage and old.get('run')==route['run']and old.get('best_over')==best['over']:
                    first=datetime.datetime.fromisoformat(old['best_first_observed_UTC'])
            observed=(now-first).total_seconds();lower=max(seconds,observed)
            out.update(stage=stage,best_over=best['over'],best_iteration=best['iteration'],last_iteration=rows[-1],
                complete_iterations_without_new_low=count,completed_iteration_seconds_since_best=seconds,
                best_first_observed_UTC=first.isoformat(),elapsed_since_best_conservative_lower_bound_s=lower,
                notify_root_for_stall_decision=(count>=3 and lower>=540 and not out['completion_observed']),
                rule='At least3completeiterationsand540swithoutstrictnewbest; rootdecides, noautotermination',iterations=rows)
    write(destination,out)
    print(json.dumps({k:v for k,v in out.items()if k!='iterations'}))

if __name__=='__main__':main()
